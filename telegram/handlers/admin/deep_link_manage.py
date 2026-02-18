from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.deep_linking import create_start_link
from filters import IsMainAdmin
from filters import TextBtn as __
from keyboards import *
from loader import bot, db_manage, dp
from locales import get_text as _
from utils.states import StateCreateDeepLink


# Меню создания диплинка подписки
@dp.message(__("btn_create_deep_link"), IsMainAdmin())
async def deep_link_menu(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(StateCreateDeepLink.days)

    await message.answer(
        text=_("deep_link_enter_days"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=_("btn_cancel"), callback_data="cancel_deep_link"
                    )
                ]
            ]
        ),
    )


# Обработка отмены
@dp.callback_query(F.data == "cancel_deep_link", IsMainAdmin())
async def cancel_deep_link(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await query.message.edit_text(_("deep_link_canceled"))


# Получение количества дней и генерация диплинка
@dp.message(StateCreateDeepLink.days, IsMainAdmin())
async def process_deep_link_days(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer(_("deep_link_positive_integer"))
        return

    # Генерируем уникальный deep_link
    deep_link_str = await db_manage.create_deep_link(days)

    # Создаем стартовую ссылку
    start_link = await create_start_link(bot=bot, payload=deep_link_str)

    await state.clear()
    await message.answer(
        text=_(
            "deep_link_created",
            days=days,
            start_link=start_link,
            deep_link_str=deep_link_str,
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=_("btn_main_menu"), callback_data="start")]
            ]
        ),
    )


# Просмотр списка созданных диплинков
@dp.callback_query(F.data == "list_deep_links", IsMainAdmin())
async def list_deep_links_handler(query: CallbackQuery):
    deep_links = await db_manage.list_deep_links()
    if not deep_links:
        await query.message.answer(_("deep_link_no_links"))
        return

    text_lines = ["<b>Список диплинков подписки:</b>\n"]
    for dl in deep_links:
        status = "🟢 Активен" if dl.is_active else "🔴 Использован"
        activated = (
            f", активирован пользователем {dl.activated_by_user_id}"
            if dl.activated_at
            else ""
        )
        text_lines.append(
            f"• <code>{dl.deep_link}</code> — {dl.duration_days} дней ({status}){activated}"
        )

    await query.message.answer("\n".join(text_lines))
