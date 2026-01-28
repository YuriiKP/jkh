from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from keyboards.text import *



def user_menu(trial: str):
    builder = InlineKeyboardBuilder()
    
    if trial == 'true':
        builder.button(text=btn_trial_buy, callback_data='trial_bay')
        builder.button(text=btn_my_key, callback_data='my_key')
        builder.button(text=btn_buy, callback_data='buy')
    else:
        builder.button(text=btn_buy, callback_data='buy')
        builder.button(text=btn_my_key, callback_data='my_key')
    
    builder.button(text=btn_help, callback_data='help')
    builder.adjust(1, 2)
    
    return builder.as_markup()


def help_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text=btn_how_to_connect, callback_data='how_to_connect')
    builder.button(text=btn_main_menu, callback_data='start')
    builder.adjust(1)
    
    return builder.as_markup()


def buy_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text=btn_buy_one_month, callback_data='btn_buy_one_month')
    builder.button(text=btn_main_menu, callback_data='start')
    builder.adjust(1)
    
    return builder.as_markup()


def user_payment_method_menu():
    """Меню выбора способа оплаты (карта, звезды или поддержка)."""
    builder = InlineKeyboardBuilder()
    
    builder.button(text=btn_pay_with_card, callback_data='btn_pay_with_card')
    builder.button(text=btn_pay_with_stars, callback_data='btn_pay_with_stars')
    builder.button(text=btn_pay_with_support, callback_data='btn_pay_with_support')
    builder.button(text=btn_back, callback_data='buy')

    builder.adjust(1)
    return builder.as_markup()



admin_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=about_users_bot)]
    ],
    resize_keyboard=True
)


main_admin_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=btn_admins), KeyboardButton(text=about_users_bot)],
        [KeyboardButton(text=btn_create_deep_link)]
    ],
    resize_keyboard=True
)