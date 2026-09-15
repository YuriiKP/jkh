from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from keyboards import buy_menu, user_payment_method_menu
from loader import dp
from locales import get_text as _
from tariffs import CALLBACK_PREFIX, get_tariff, tariff_from_callback
from utils.states import StateTariffSelection

from ..common import edit_menu_with_image


# Обработчик кнопки "Купить"
@dp.callback_query(F.data == "buy")
async def buy_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    # Редактируем меню с изображением
    await edit_menu_with_image(
        event=query, text=_("user_buy_text"), reply_markup=buy_menu()
    )


# ========== ВЫБОР ТАРИФА ==========


@dp.callback_query(F.data.startswith(CALLBACK_PREFIX))
async def select_tariff_handler(query: CallbackQuery, state: FSMContext):
    """Единый обработчик выбора тарифа: тариф определяется по callback_data."""
    tariff = tariff_from_callback(query.data)

    await state.clear()
    await state.set_state(StateTariffSelection.tariff)
    await state.update_data(tariff=tariff.key)

    # Показываем меню выбора способа оплаты
    await edit_menu_with_image(
        event=query,
        text=_("payment_method_text"),
        reply_markup=user_payment_method_menu(),
    )


# ========== ОПЛАТА ==========


@dp.callback_query(F.data == "btn_pay_with_stars")
async def pay_with_stars_handler(query: CallbackQuery, state: FSMContext):
    # Получаем выбранный тариф из состояния ДО очистки
    state_data = await state.get_data()
    tariff = get_tariff(state_data.get("tariff"))
    await state.clear()

    # 1. Формируем цену
    prices = [LabeledPrice(label=f"{tariff.title} VPN", amount=tariff.stars)]

    # 2. Отправляем инвойс
    if query.message:
        await query.message.answer_invoice(
            title=f"Подписка на {tariff.title}",
            description=f"ЖКХ подписка на {tariff.days} дней",
            prices=prices,
            payload=tariff.key,  # id тарифа
            currency="XTR",  # Код валюты для звезд тг
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=_("payment_pay_stars", stars=tariff.stars), pay=True
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=_("payment_cancel"),
                            callback_data="buy",
                            style="danger",
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
