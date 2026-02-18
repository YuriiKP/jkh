from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from locales import get_text as _

from keyboards.text import *


def user_menu(trial: str):
    builder = InlineKeyboardBuilder()

    if trial == "true":
        builder.button(text=_("btn_trial_buy"), callback_data="trial_bay")
        builder.button(text=_("btn_buy"), callback_data="buy")
    else:
        builder.button(text=_("btn_buy"), callback_data="buy")

    builder.button(text=_("btn_profile"), callback_data="btn_profile")
    builder.button(text=_("btn_help"), callback_data="help")
    builder.adjust(1, 2)

    return builder.as_markup()


def rules_menu():
    builder = InlineKeyboardBuilder()

    builder.button(text=_("btn_rules_accept"), callback_data="btn_rules_accept")
    builder.button(text=_("btn_rules_decline"), callback_data="btn_rules_decline")

    builder.adjust(1)

    return builder.as_markup()


def help_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text=_("btn_how_to_connect"), callback_data="how_to_connect")
    builder.button(text=_("btn_main_menu"), callback_data="start")
    builder.adjust(1)

    return builder.as_markup()


def buy_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text=_("btn_buy_one_month"), callback_data="btn_buy_one_month")
    builder.button(text=_("btn_main_menu"), callback_data="start")
    builder.adjust(1)

    return builder.as_markup()


def user_payment_method_menu():
    """Меню выбора способа оплаты (карта, звезды или поддержка)."""
    builder = InlineKeyboardBuilder()

    builder.button(text=_("btn_pay_with_card"), callback_data="btn_pay_with_card")
    builder.button(text=_("btn_pay_with_stars"), callback_data="btn_pay_with_stars")
    builder.button(text=_("btn_pay_with_support"), callback_data="btn_pay_with_support")
    builder.button(text=_("btn_back"), callback_data="buy")

    builder.adjust(1)
    return builder.as_markup()


def user_btn_main_menu():
    """Меню с одной кнопкой выхода в главное меню."""
    builder = InlineKeyboardBuilder()

    builder.button(text=_("btn_main_menu"), callback_data="start")

    builder.adjust(1)
    return builder.as_markup()


def user_my_keys_stat_menu():
    """Меню с одной кнопкой выхода в главное меню."""
    builder = InlineKeyboardBuilder()

    builder.button(text=_("btn_how_to_connect"), callback_data="how_to_connect")
    builder.button(text=_("btn_get_qr_code"), callback_data="get_qr_code")
    builder.button(text=_("btn_main_menu"), callback_data="start")

    builder.adjust(1)
    return builder.as_markup()


def user_my_keys_qr_code():
    """Меню с одной кнопкой выхода в главное меню."""
    builder = InlineKeyboardBuilder()

    builder.button(text=_("btn_how_to_connect"), callback_data="how_to_connect")
    builder.button(text=_("btn_main_menu"), callback_data="start")

    builder.adjust(1)
    return builder.as_markup()


def profile_menu():
    """Меню профиля пользователя."""
    builder = InlineKeyboardBuilder()

    builder.button(text=_("btn_my_key"), callback_data="my_key")
    builder.button(text=_("btn_language"), callback_data="language")
    builder.button(text=_("btn_back_to_main"), callback_data="start")

    builder.adjust(2, 1)
    return builder.as_markup()


def language_menu():
    """Меню выбора языка."""
    builder = InlineKeyboardBuilder()

    builder.button(text=_("btn_lang_ru"), callback_data="btn_lang_ru")
    builder.button(text=_("btn_lang_en"), callback_data="btn_lang_en")
    builder.button(text=_("btn_back"), callback_data="btn_profile")

    builder.adjust(1)
    return builder.as_markup()


def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=_("about_users_bot"))]], resize_keyboard=True
    )


def main_admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=_("btn_admins")),
                KeyboardButton(text=_("about_users_bot")),
            ],
            [KeyboardButton(text=_("btn_create_deep_link"))],
        ],
        resize_keyboard=True,
    )
