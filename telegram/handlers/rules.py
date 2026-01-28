from datetime import datetime, timedelta
from aiogram.types import Message, CallbackQuery, BotCommandScopeDefault, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram import F
from aiogram.exceptions import TelegramBadRequest

from loader import dp, bot, deep_links_admin_manage, db_manage, marzban_client
from models.user import UserCreate, UserStatusCreate, UserModify, UserStatusModify
from models.proxy import ProxyTable, VlessSettings, XTLSFlows
from utils.marzban_api import MarzbanAPIError
from keyboards import *
from filters import IsAdmin, IsMainAdmin, IsUser
from commands import user_commands

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