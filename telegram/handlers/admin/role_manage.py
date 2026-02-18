from random import randint

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.deep_linking import create_start_link
from filters import IsAdmin, IsMainAdmin
from filters import TextBtn as __
from keyboards import *
from loader import TG_ADMIN, bot, db_manage, deep_links_admin_manage, dp, symbols
from utils import CB_ModerAdmins, State_Ban_Admin


################################################################################
# Управление админами
@dp.message(__("btn_admins"), IsMainAdmin())
async def admin_manage_menu(message: Message, state: FSMContext):
    await state.clear()

    admins = await db_manage.get_admins()

    text = f"<b>{_('admin_all_administrators')}</b>"
    for admin in admins:
        if int(admin[0]) == int(TG_ADMIN):
            pass
        else:
            text += f'\n\n{admin[5]} <a href="tg://user?id={admin[0]}">{admin[2]}</a> ID: {admin[0]}'

    await message.answer(
        text=text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=_("admin_add_admin"), callback_data="add_admin"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=_("admin_demote_admin"), callback_data="ban_admin"
                    )
                ],
            ]
        ),
    )


# Кого добавить
@dp.callback_query(F.data == "add_admin", IsMainAdmin())
async def choice_add_admin(query: CallbackQuery, state: FSMContext):
    await query.message.answer(
        text=_("admin_who_to_add"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=_("admin_main_admin"),
                        callback_data=CB_ModerAdmins(
                            action="add_admin", status_user="main_admin"
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=_("admin_admin"),
                        callback_data=CB_ModerAdmins(
                            action="add_admin", status_user="admin"
                        ).pack(),
                    )
                ],
            ]
        ),
    )


# Создание ссылки
@dp.callback_query(CB_ModerAdmins.filter(F.action == "add_admin"), IsMainAdmin())
async def prpcess_add_admin(
    query: CallbackQuery, state: FSMContext, callback_data: CB_ModerAdmins
):
    status_user = callback_data.status_user

    str_link = ""
    for _ in range(5):
        str_link += symbols[randint(0, 35)]

    start_link = await create_start_link(bot=bot, payload=str_link)

    deep_links_admin_manage[str_link] = status_user

    await query.message.answer(text=start_link)


# Удаление админа
@dp.callback_query(F.data == "ban_admin", IsMainAdmin())
async def process_ban_admin(query: CallbackQuery, state: FSMContext):
    await state.set_state(State_Ban_Admin.msg)

    await query.message.answer(text=_("admin_send_user_id"))


# Полчение ид пользователя
@dp.message(State_Ban_Admin.msg, IsMainAdmin())
async def ban_admin(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)

        await db_manage.update_user(user_id=user_id, status_user="user")

        await message.answer(text=_("admin_user_removed", user_id=message.text))

        await state.clear()

    except TypeError and ValueError:
        await message.answer(text=_("admin_user_not_found"))
