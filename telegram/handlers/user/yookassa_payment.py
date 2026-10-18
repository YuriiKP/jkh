import asyncio
import logging
import time

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loader import (
    YOO_KASSA_RETURN_URL,
    db_manage,
    dp,
    yookassa_client,
)
from locales import get_text as _
from tariffs import get_tariff

from ..common import edit_menu_with_image

logger = logging.getLogger(__name__)

# Окно идемпотентности (секунды). Повторное нажатие «Оплатить» в пределах этого
# интервала переиспользует уже созданный платёж, а не создаёт второй.
# Это защищает от дублей, когда Telegram/nginx переотправляет один и тот же
# апдейт (в логе такие апдейты видны как обработанные дважды).
PAYMENT_IDEMPOTENCE_WINDOW = 120

# Локи по пользователю: одновременная обработка двух копий одного апдейта
# не должна приводить к двум запросам на создание платежа.
_user_locks: dict[int, asyncio.Lock] = {}


def _get_user_lock(user_id: int) -> asyncio.Lock:
    """Возвращает (создавая при необходимости) лок для конкретного пользователя."""
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _user_locks[user_id] = lock
    return lock


def _build_idempotence_key(user_id: int, tariff_key: str) -> str:
    """
    Строит детерминированный ключ идемпотентности ЮKassa.

    Ключ одинаков для всех повторов в пределах PAYMENT_IDEMPOTENCE_WINDOW,
    поэтому повторный запрос с тем же ключом вернёт уже созданный платёж.
    """
    bucket = int(time.time()) // PAYMENT_IDEMPOTENCE_WINDOW
    return f"yookassa-{user_id}-{tariff_key}-{bucket}"


def _build_payment_keyboard(payment_link: str, rub_amount: float, user_id: int):
    """Собирает клавиатуру экрана оплаты: ссылка, проверка статуса, отмена."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=_("payment_pay_rub", amount=rub_amount),
        url=payment_link,
        style="primary",
    )
    builder.button(
        text=_("payment_check_status"), callback_data=f"check_payment:{user_id}"
    )
    builder.button(text=_("payment_cancel"), callback_data="buy", style="danger")
    builder.adjust(1)
    return builder.as_markup()


@dp.callback_query(F.data == "btn_pay_with_yookassa")
async def pay_with_yookassa_handler(query: CallbackQuery, state: FSMContext):
    """
    Обработчик для создания платежа через ЮKassa.
    """
    if not yookassa_client:
        await query.answer(_("payment_service_unavailable"), show_alert=True)
        return

    # Сразу гасим «крутилку» на кнопке — дальше обработка может занять время.
    # Отвечать на callback можно только один раз, поэтому все alert-ветки
    # должны идти до этого вызова.
    await query.answer()

    # Получаем выбранный тариф из состояния
    state_data = await state.get_data()
    tariff = get_tariff(state_data.get("tariff"))

    user_id = query.from_user.id
    rub_amount = float(tariff.rub)

    # Создание платежа — под локом, чтобы дублирующий апдейт не создал
    # второй платёж параллельно (идемпотентный ключ ниже страхует
    # от дублей уже на стороне ЮKassa).
    lock = _get_user_lock(user_id)
    async with lock:
        payment_link = await yookassa_client.create_payment_link(
            amount=rub_amount,
            currency="RUB",
            description=f"Оплата сервиса ({tariff.title})",
            user_id=user_id,
            return_url=YOO_KASSA_RETURN_URL,
            metadata={
                "product": "service_access",
                "period": f"{tariff.days}_days",
                "tariff": tariff.key,
            },
            idempotence_key=_build_idempotence_key(user_id, tariff.key),
        )

    if not payment_link:
        # Callback уже отвечен, поэтому alert показать нельзя — показываем
        # экран с ошибкой и кнопкой повтора.
        builder = InlineKeyboardBuilder()
        builder.button(
            text=_("btn_try_again"),
            callback_data="btn_pay_with_yookassa",
            style="primary",
        )
        builder.button(text=_("payment_cancel"), callback_data="buy", style="danger")
        builder.adjust(1)

        await edit_menu_with_image(
            event=query,
            text=_("payment_creation_failed"),
            reply_markup=builder.as_markup(),
        )
        return

    await edit_menu_with_image(
        event=query,
        text=_("yookassa_payment_instructions"),
        reply_markup=_build_payment_keyboard(payment_link, rub_amount, user_id),
    )


@dp.callback_query(F.data.startswith("check_payment:"))
async def check_payment_status_handler(query: CallbackQuery, state: FSMContext):
    """
    Обработчик для проверки статуса платежа.
    """
    if not yookassa_client:
        await query.answer(_("payment_service_unavailable"), show_alert=True)
        return

    # Извлекаем user_id из callback_data (не переопределяем функцию перевода `_`)
    try:
        user_id = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await query.answer(_("invalid_request"), show_alert=True)
        return

    # Проверять можно только свой платёж: user_id берётся из callback_data,
    # которую пользователь может подделать.
    if user_id != query.from_user.id:
        logger.warning(
            f"Пользователь {query.from_user.id} пытается проверить "
            f"платёж пользователя {user_id}"
        )
        await query.answer(_("invalid_request"), show_alert=True)
        return

    # Отвечаем на callback ровно один раз — после всех проверок
    await query.answer()

    await state.clear()

    # Проверяем, есть ли успешные платежи у пользователя
    payments = await db_manage.get_payments_by_user(user_id)

    # Ищем последний успешный платеж
    successful_payment = None
    for payment in payments:
        if payment["status"] == "completed":
            successful_payment = payment
            break

    if successful_payment:
        # Если есть успешный платеж, показываем информацию о подписке
        builder = InlineKeyboardBuilder()
        builder.button(text=_("btn_profile"), callback_data="btn_profile")
        builder.button(text=_("btn_main_menu"), callback_data="start")
        builder.adjust(1)

        await edit_menu_with_image(
            event=query,
            text=_("payment_already_processed"),
            reply_markup=builder.as_markup(),
        )
    else:
        # Если платежа нет, предлагаем оплатить снова
        builder = InlineKeyboardBuilder()
        builder.button(
            text=_("btn_try_again"),
            callback_data="btn_pay_with_yookassa",
            style="primary",
        )
        builder.button(text=_("btn_back"), callback_data="buy")
        builder.adjust(1)

        await edit_menu_with_image(
            event=query, text=_("payment_not_found"), reply_markup=builder.as_markup()
        )
