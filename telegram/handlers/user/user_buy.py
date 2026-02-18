from datetime import datetime, timedelta

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from keyboards import *
from loader import YOO_KASSA_PROVIDER_TOKEN, db_manage, dp, marzban_client
from locales import get_text as _
from models.proxy import ProxyTable, VlessSettings, XTLSFlows
from models.user import (
    UserCreate,
    UserModify,
    UserResponse,
    UserStatusCreate,
    UserStatusModify,
)
from utils.marzban_api import MarzbanAPIError

from ..common import edit_menu_with_image


# Обработчик кнопки "Купить"
@dp.callback_query(F.data == "buy")
async def buy_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    # Редактируем меню с изображением
    await edit_menu_with_image(
        event=query, text=_("user_buy_text"), reply_markup=buy_menu()
    )


@dp.callback_query(F.data == "btn_buy_one_month")
async def buy_one_month_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    # Показываем меню выбора способа оплаты
    await edit_menu_with_image(
        event=query,
        text=_("payment_method_text"),
        reply_markup=user_payment_method_menu(),
    )


@dp.callback_query(F.data == "btn_pay_with_card")
async def pay_with_card_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    # Цена в копейках (2 рубля = 200 копеек)
    prices = [LabeledPrice(label="1 месяц VPN", amount=10000)]

    # provider_data для ЮKassa с указанием метода оплаты СБП
    # provider_data = '{"payment_method_type": "sbp"}'

    # Отправляем инвойс с провайдером ЮKassa
    if query.message:
        await query.message.answer_invoice(
            title="Подписка на 1 месяц",
            description="ЖКХ подписка на 30 дней",
            prices=prices,
            payload="one_month",  # id тарифа
            currency="RUB",  # Код валюты для рублёвых платежей
            provider_token=YOO_KASSA_PROVIDER_TOKEN,
            # provider_data=provider_data,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=_("payment_pay_100_rub"), pay=True)],
                    [
                        InlineKeyboardButton(
                            text=_("payment_cancel"), callback_data="buy"
                        )
                    ],
                ]
            ),
        )

        await query.message.delete()


@dp.callback_query(F.data == "btn_pay_with_stars")
async def pay_with_stars_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    # 1. Формируем цену
    prices = [LabeledPrice(label="1 месяц VPN", amount=55)]

    # 2. Отправляем инвойс
    if query.message:
        await query.message.answer_invoice(
            title="Подписка на 1 месяц",
            description="ЖКХ подписка на 30 дней",
            prices=prices,
            payload="one_month",  # id тарифа
            currency="XTR",  # Код валюты для звезд тг
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=_("payment_pay_55_stars"), pay=True)],
                    [
                        InlineKeyboardButton(
                            text=_("payment_cancel"), callback_data="buy"
                        )
                    ],
                ]
            ),
        )

        await query.message.delete()


@dp.callback_query(F.data == "btn_pay_with_support")
async def pay_with_support_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.button(text=_("payment_contact_support"), url="https://t.me/foteleg_b")
    builder.button(text=_("btn_back"), callback_data="buy")
    builder.adjust(1)

    # Редактируем меню с изображением
    await edit_menu_with_image(
        event=query, text=_("support_payment_text"), reply_markup=builder.as_markup()
    )


# Обработака успешной оплаты
@dp.message(F.successful_payment)
async def success_payment_handler(message: Message):
    payment_info = message.successful_payment

    if payment_info and payment_info.invoice_payload == "one_month":
        user_id = message.from_user.id

        # Если есть не активированай пробный период, отменям его
        user_tg = await db_manage.get_user_by_id(user_id)
        if user_tg and user_tg[7] == "true":
            await db_manage.update_user(user_id, trial="false")

        # Если пользователя в marzban нет создаем его
        try:
            user_marz: UserResponse = await marzban_client.get_user(str(user_id))

            # Определяем текущую дату истечения
            if user_marz.expire:
                # Если expire это timestamp (int), конвертируем в datetime
                if isinstance(user_marz.expire, int):
                    current_expire = datetime.fromtimestamp(user_marz.expire)
                else:
                    current_expire = user_marz.expire
                    # Если datetime имеет timezone, конвертируем в naive datetime
                    if current_expire.tzinfo is not None:
                        current_expire = current_expire.replace(tzinfo=None)
            else:
                # Если подписки нет, начинаем с текущей даты
                current_expire = datetime.now()

            # Добавляем 30 дней к текущей дате истечения
            new_expire = current_expire + timedelta(days=30)

            modify_user = UserModify(
                expire=new_expire,
                proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION)),
                status=UserStatusModify.active,
            )
            user_marz: UserResponse = await marzban_client.modify_user(
                str(user_id), modify_user
            )
        except MarzbanAPIError as e:
            if e.status == 404:
                new_user = UserCreate(
                    username=str(user_id),
                    note=f"{message.from_user.first_name or ''} @{message.from_user.username or ''}",
                    status=UserStatusCreate.active,
                    expire=datetime.now() + timedelta(days=30),
                    group_ids=[1],
                    proxy_settings=ProxyTable(
                        vless=VlessSettings(flow=XTLSFlows.VISION)
                    ),
                )
                user_marz: UserResponse = await marzban_client.create_user(new_user)

            else:
                print(e.message)

        # Сохраняем информацию о платеже в базе данных
        if payment_info:
            await db_manage.add_payment(
                user_id=user_id,
                amount=payment_info.total_amount,
                currency=payment_info.currency,
                payload=payment_info.invoice_payload,
                telegram_payment_charge_id=payment_info.telegram_payment_charge_id,
                provider_payment_charge_id=payment_info.provider_payment_charge_id,
                status="completed",
            )

        await message.answer("Оплата прошла успешно! Ваша подписка обновлена. 🚀")
        if user_marz:
            await message.answer(
                text=my_keys_stat_info(user_marz),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=btn_how_to_connect, callback_data="how_to_connect"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text=btn_main_menu, callback_data="start"
                            )
                        ],
                    ]
                ),
            )
