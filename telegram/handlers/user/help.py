from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message
from keyboards import *
from loader import dp

from ..common import edit_menu_with_image


@dp.message(Command("help"))
async def help_command(message: Message, state: FSMContext):
    await state.clear()
    await process_help(message)


@dp.callback_query(F.data == "help")
async def help_query(query: CallbackQuery, state: FSMContext):
    await state.clear()
    if query.message:
        await process_help(query.message)


async def process_help(message: Message | None):
    # Редактируем меню с изображением
    if message:
        await edit_menu_with_image(
            event=message, text=help_text, reply_markup=help_menu()
        )


# Обработчик кнопки "Как подключиться"
@dp.callback_query(F.data == "how_to_connect")
async def how_to_connect_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.button(text=btn_main_menu, callback_data="start")
    builder.adjust(1)

    # Редактируем меню с изображением
    await edit_menu_with_image(
        event=query, text=help_manual_text, reply_markup=builder.as_markup()
    )
