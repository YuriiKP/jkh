from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram import F
from aiogram.exceptions import TelegramBadRequest

from loader import dp
from keyboards import *
from handlers.start import process_start_bot



@dp.callback_query(F.data == 'btn_rules_accept')
async def rules_accept_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    try:
        await query.message.delete()
    except TelegramBadRequest:
        pass

    await process_start_bot(query.message, query.from_user.id)


@dp.callback_query(F.data == 'btn_rules_decline')
async def rules_decline_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    warning_text = '❗️ Чтобы продолжить пользоватсья сервисом, нужно принять правила!'

    try:
        await query.message.edit_text(
            text=warning_text,
            reply_markup=rules_menu()
        )
    except TelegramBadRequest:
        await query.message.answer(
            text=warning_text,
            reply_markup=rules_menu()
        )