import asyncio

from aiogram import F
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from filters import IsAdmin
from filters import TextBtn as __
from keyboards import *
from loader import bot, db_manage, dp
from locales import get_text as _
from utils import State_Mailing


# Показать кол-во юзеров
@dp.message(__("about_users_bot"), IsAdmin())
async def show_info_about_users_bot(message: Message, state: FSMContext):
    await state.clear()

    all_users = await db_manage.count_users()

    text = _("admin_users_info", all_users=all_users)

    await message.answer(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=_("admin_make_mailing"), callback_data="mailing"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=_("admin_download_ids"), callback_data="down_users_id"
                    )
                ],
            ]
        ),
    )


# Выгрузка id всех пользователей
@dp.callback_query(F.data == "down_users_id", IsAdmin())
async def down_users_id(query: CallbackQuery, state: FSMContext):
    users_id = await db_manage.get_users_id()

    users_id_str = ""
    for user_id in users_id:
        users_id_str += f"{user_id[0]}\n"

    await query.message.answer_document(
        document=BufferedInputFile(file=users_id_str.encode(), filename="users.txt")
    )


# Настройка рассылки
@dp.callback_query(F.data == "mailing", IsAdmin())
async def setting_mailing(query: CallbackQuery, state: FSMContext):
    await state.set_state(State_Mailing.msg)

    await query.message.answer(
        text=_("admin_send_mailing_message"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=_("admin_cancel"), callback_data="stop_mailing"
                    )
                ]
            ]
        ),
    )


# Отмена рассылки
@dp.callback_query(F.data == "stop_mailing", IsAdmin())
async def stop_mailing(query: CallbackQuery, state: FSMContext):
    await show_info_about_users_bot(query.message, state)


# Получение сообщения для расылки
@dp.message(State_Mailing.msg, IsAdmin())
async def take_msg_mailing(message: Message, state: FSMContext):
    users = await db_manage.get_users_id()
    text_buttons = []
    urls = []

    # Создаем кнопки
    async def bulding_keyboard():
        builder = InlineKeyboardBuilder()

        if text_buttons:
            for text_button, url in zip(text_buttons, urls):
                builder.button(text=text_button, url=url)

        builder.button(text=_("admin_add_button"), callback_data="add_button")
        builder.button(
            text=_("admin_start_mailing"), callback_data="confirm_start_mailing"
        )
        builder.button(text=_("admin_cancel"), callback_data="stop_mailing")

        builder.adjust(1)

        return builder.as_markup()

    # Отправляем сообщение с настройкой рассылки в чат
    async def send_settings_mailing(keyboard):
        await bot.copy_message(
            chat_id=message.from_user.id,
            from_chat_id=message.from_user.id,
            message_id=message.message_id,
            reply_markup=keyboard,
        )

    keyboard = await bulding_keyboard()
    await send_settings_mailing(keyboard)

    # Добавление кнопки
    @dp.callback_query(F.data == "add_button", IsAdmin())
    async def add_button(query: CallbackQuery, state: FSMContext):
        await state.set_state(State_Mailing.add_button)

        await query.message.answer(text=_("admin_button_format"))

    # Принимаем сообщение для кнопки
    @dp.message(State_Mailing.add_button, IsAdmin())
    async def take_button_text(message: Message, state: FSMContext):
        raw_text = message.text.split("-")
        button_text = raw_text[0].strip()
        url = raw_text[1].strip()

        text_buttons.append(button_text)
        urls.append(url)

        keyboard = await bulding_keyboard()
        await send_settings_mailing(keyboard)

    # Подтверждение рассылки
    @dp.callback_query(F.data == "confirm_start_mailing", IsAdmin())
    async def confirm_start_mailing(query: CallbackQuery, state: FSMContext):
        await query.message.answer(
            text=f"Начать рассылку?\n\nРасчетное время рассылки: {round(len(users) * 0.05, 0)}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=_("admin_start"), callback_data="start_mailing"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=_("admin_cancel"), callback_data="stop_mailing"
                        )
                    ],
                ]
            ),
        )

    # Начинаем рассылку
    @dp.callback_query(F.data == "start_mailing", IsAdmin())
    async def start_mailing(query: CallbackQuery, state: FSMContext):
        builder = InlineKeyboardBuilder()
        if text_buttons:
            for text_button, url in zip(text_buttons, urls):
                builder.button(text=text_button, url=url)
            builder.adjust(1)

        # Для расчета прогресса
        ind = round(len(users) / 5, 0)
        if ind == 0:
            ind = 1

        count_msg = []
        for index, user in enumerate(users):
            if index % ind == 0:
                await message.answer(
                    text=_("admin_mailing_progress", progress=int(index / ind * 20))
                )

            # Обработка отправки
            async def send_msg():
                try:
                    await bot.copy_message(
                        chat_id=user[0],
                        from_chat_id=message.from_user.id,
                        message_id=message.message_id,
                        reply_markup=builder.as_markup(),
                    )

                    count_msg.append(1)
                    print(f"Отправил сообщение {index + 1}")

                except TelegramRetryAfter as e:
                    print("Ошбика попробую через", e.retry_after)
                    await asyncio.sleep(e.retry_after)
                    await send_msg()

                except TelegramBadRequest as e:
                    print(e)

                except TelegramForbiddenError as e:
                    print(e)

            await send_msg()
            await asyncio.sleep(1 / 20)

        count_msg_len = len(count_msg)
        await message.answer(
            text=_(
                "admin_mailing_completed",
                total_users=len(users),
                success_count=count_msg_len,
                failed_count=len(users) - count_msg_len,
            )
        )
