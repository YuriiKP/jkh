from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from keyboards import *
from loader import dp

from handlers.start import process_start_bot

from .common import edit_menu_with_image


@dp.callback_query(F.data == "btn_rules_accept")
async def rules_accept_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    if query.message:
        try:
            await query.message.delete()
        except TelegramBadRequest:
            pass

    if query.message:
        await process_start_bot(query, query.from_user.id)


@dp.callback_query(F.data == "btn_rules_decline")
async def rules_decline_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    warning_text = "❗️ Чтобы продолжить пользоватсья сервисом, нужно принять правила!"

    # Редактируем меню с изображением
    if query.message:
        await edit_menu_with_image(
            event=query, text=warning_text, reply_markup=rules_menu()
        )
