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


# Старый обработчик для Telegram Payments удален
# Используйте новый обработчик btn_pay_with_yookassa для прямой интеграции с ЮKassa


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


# Обработчик успешной оплаты через Telegram Payments удален
# Используйте вебхук ЮKassa для обработки платежей
