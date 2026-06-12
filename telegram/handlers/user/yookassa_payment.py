from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from keyboards import *
from loader import (
    PRICE_1M_RUB,
    PRICE_1M_STARS,
    PRICE_3M_RUB,
    PRICE_3M_STARS,
    PRICE_6M_RUB,
    PRICE_6M_STARS,
    YOO_KASSA_RETURN_URL,
    db_manage,
    dp,
    yookassa_client,
)
from locales import get_text as _
from utils.states import StateTariffSelection

from ..common import edit_menu_with_image

# Словарь тарифов (дублируем для использования в этом файле)
TARIFFS = {
    "one_month": {
        "label": "1 месяц",
        "days": 30,
        "rub": PRICE_1M_RUB,
        "stars": PRICE_1M_STARS,
    },
    "three_months": {
        "label": "3 месяца",
        "days": 90,
        "rub": PRICE_3M_RUB,
        "stars": PRICE_3M_STARS,
    },
    "six_months": {
        "label": "6 месяцев",
        "days": 180,
        "rub": PRICE_6M_RUB,
        "stars": PRICE_6M_STARS,
    },
}


@dp.callback_query(F.data == "btn_pay_with_yookassa")
async def pay_with_yookassa_handler(query: CallbackQuery, state: FSMContext):
    """
    Обработчик для создания платежа через ЮKassa.
    """
    # Получаем выбранный тариф из состояния ДО очистки
    state_data = await state.get_data()
    tariff_key = state_data.get("tariff", "one_month")
    tariff_info = TARIFFS.get(tariff_key, TARIFFS["one_month"])
    await state.clear()

    if not yookassa_client:
        await query.answer(_("payment_service_unavailable"), show_alert=True)
        return

    user_id = query.from_user.id
    rub_amount = float(tariff_info["rub"])
    label = tariff_info["label"]
    days = tariff_info["days"]

    # Создаем ссылку на оплату
    payment_link = await yookassa_client.create_payment_link(
        amount=rub_amount,
        currency="RUB",
        description=f"Подписка на {label} VPN",
        user_id=user_id,
        return_url=YOO_KASSA_RETURN_URL,
        metadata={
            "product": "vpn_subscription",
            "period": f"{days}_days",
            "tariff": tariff_key,
        },
    )

    if not payment_link:
        await query.answer(_("payment_creation_failed"), show_alert=True)
        return

    # Создаем клавиатуру с кнопкой для оплаты
    builder = InlineKeyboardBuilder()
    builder.button(text=_("payment_pay_rub", amount=rub_amount), url=payment_link)
    builder.button(
        text=_("payment_check_status"), callback_data=f"check_payment:{user_id}"
    )
    builder.button(text=_("payment_cancel"), callback_data="buy")
    builder.adjust(1)

    # Отправляем сообщение со ссылкой на оплату
    await edit_menu_with_image(
        event=query,
        text=_("yookassa_payment_instructions"),
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("check_payment:"))
async def check_payment_status_handler(query: CallbackQuery, state: FSMContext):
    """
    Обработчик для проверки статуса платежа.
    """
    await state.clear()

    if not yookassa_client:
        await query.answer(_("payment_service_unavailable"), show_alert=True)
        return

    # Извлекаем user_id из callback_data
    try:
        _, user_id_str = query.data.split(":")
        user_id = int(user_id_str)
    except (ValueError, IndexError):
        await query.answer(_("invalid_request"), show_alert=True)
        return

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
        builder.button(text=_("btn_my_keys"), callback_data="my_keys")
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
        builder.button(text=_("btn_try_again"), callback_data="btn_pay_with_yookassa")
        builder.button(text=_("btn_back"), callback_data="buy")
        builder.adjust(1)

        await edit_menu_with_image(
            event=query, text=_("payment_not_found"), reply_markup=builder.as_markup()
        )
