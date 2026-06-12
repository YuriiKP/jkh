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
from loader import (
    PRICE_1M_RUB,
    PRICE_1M_STARS,
    PRICE_3M_RUB,
    PRICE_3M_STARS,
    PRICE_6M_RUB,
    PRICE_6M_STARS,
    YOO_KASSA_PROVIDER_TOKEN,
    db_manage,
    dp,
    marzban_client,
)
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
from utils.states import StateTariffSelection

from ..common import edit_menu_with_image

# Словарь соответствия тарифов: callback_data -> (название, дней, рублей, звезд)
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


def _get_tariff_info(tariff_key: str) -> dict | None:
    """Возвращает информацию о тарифе по ключу."""
    return TARIFFS.get(tariff_key)


# Обработчик кнопки "Купить"
@dp.callback_query(F.data == "buy")
async def buy_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    # Редактируем меню с изображением
    await edit_menu_with_image(
        event=query, text=_("user_buy_text"), reply_markup=buy_menu()
    )


# ========== ОБРАБОТЧИКИ ВЫБОРА ТАРИФА ==========


@dp.callback_query(F.data == "btn_buy_one_month")
async def buy_one_month_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(StateTariffSelection.tariff)
    await state.update_data(tariff="one_month")

    # Показываем меню выбора способа оплаты
    await edit_menu_with_image(
        event=query,
        text=_("payment_method_text"),
        reply_markup=user_payment_method_menu(),
    )


@dp.callback_query(F.data == "btn_buy_three_months")
async def buy_three_months_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(StateTariffSelection.tariff)
    await state.update_data(tariff="three_months")

    # Показываем меню выбора способа оплаты
    await edit_menu_with_image(
        event=query,
        text=_("payment_method_text"),
        reply_markup=user_payment_method_menu(),
    )


@dp.callback_query(F.data == "btn_buy_six_months")
async def buy_six_months_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(StateTariffSelection.tariff)
    await state.update_data(tariff="six_months")

    # Показываем меню выбора способа оплаты
    await edit_menu_with_image(
        event=query,
        text=_("payment_method_text"),
        reply_markup=user_payment_method_menu(),
    )


# ========== ОБРАБОТЧИКИ ОПЛАТЫ ==========


@dp.callback_query(F.data == "btn_pay_with_stars")
async def pay_with_stars_handler(query: CallbackQuery, state: FSMContext):
    # Получаем выбранный тариф из состояния ДО очистки
    state_data = await state.get_data()
    tariff_key = state_data.get("tariff", "one_month")
    await state.clear()

    tariff_info = _get_tariff_info(tariff_key)

    stars_amount = tariff_info["stars"]
    label = tariff_info["label"]

    # 1. Формируем цену
    prices = [LabeledPrice(label=f"{label} VPN", amount=stars_amount)]

    # 2. Отправляем инвойс
    if query.message:
        await query.message.answer_invoice(
            title=f"Подписка на {label}",
            description=f"ЖКХ подписка на {tariff_info['days']} дней",
            prices=prices,
            payload=tariff_key,  # id тарифа
            currency="XTR",  # Код валюты для звезд тг
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=_("payment_pay_stars", stars=stars_amount), pay=True
                        )
                    ],
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
