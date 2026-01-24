from aiogram.types import Message, CallbackQuery, LinkPreviewOptions
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram import F

from loader import dp
from keyboards import *



@dp.message(Command('help'))
async def help_command(message: Message, state: FSMContext):
    await state.clear()
    await process_help(message)


@dp.callback_query(F.data == 'help')
async def help_query(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await process_help(query.message)


async def process_help(message: Message):
    try:
        await message.edit_text(
            text=help_text,
            reply_markup=help_menu()
        )
    except TelegramBadRequest:
        await message.answer(
            text=help_text,
            reply_markup=help_menu()
        )


# Обработчик кнопки "Как подключиться"
@dp.callback_query(F.data == 'how_to_connect')
async def how_to_connect_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    
    builder = InlineKeyboardBuilder()
    builder.button(text=btn_main_menu, callback_data='start')
    builder.adjust(1)

    try:
        await query.message.edit_text(
            text=help_manual_text,
            reply_markup=builder.as_markup(),
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
    except TelegramBadRequest:
        await query.message.answer(
            text=help_manual_text,
            reply_markup=builder.as_markup(),
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )

