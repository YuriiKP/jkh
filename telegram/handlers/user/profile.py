from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from keyboards import *
from loader import db_manage, dp
from locales import get_text as _
from locales import update_lang

from ..common import edit_menu_with_image


# Обработчик кнопки "Профиль"
@dp.callback_query(F.data == "btn_profile")
async def profile_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    user_id = query.from_user.id
    user = await db_manage.get_user_by_id(user_id)

    if user:
        current_lang = user[6]  # language находится на 6-й позиции (индекс 6)
        lang_display = "🇷🇺 Русский" if current_lang == "ru" else "🇬🇧 English"

        profile_text = _(
            "profile_text",
            user_id=query.from_user.id,
            language=lang_display,
        )
    else:
        profile_text = _("profile_default_text")

    await edit_menu_with_image(
        event=query, text=profile_text, reply_markup=profile_menu()
    )


# Обработчик кнопки "Язык"
@dp.callback_query(F.data == "language")
async def language_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    language_text = _("language_selection_text")

    await edit_menu_with_image(
        event=query, text=language_text, reply_markup=language_menu()
    )


# Обработчик выбора русского языка
@dp.callback_query(F.data == "btn_lang_ru")
async def lang_ru_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    user_id = query.from_user.id
    await db_manage.update_user(user_id=user_id, language="ru")

    # Обновляем контекст языка
    update_lang("ru")

    await query.answer(_("language_changed_ru"))

    # Возвращаемся в меню профиля
    profile_text = _(
        "profile_text",
        user_id=user_id,
        language="🇷🇺 Русский",
    )

    await edit_menu_with_image(
        event=query, text=profile_text, reply_markup=profile_menu()
    )


# Обработчик выбора английского языка
@dp.callback_query(F.data == "btn_lang_en")
async def lang_en_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    user_id = query.from_user.id
    await db_manage.update_user(user_id=user_id, language="en")

    # Обновляем контекст языка
    update_lang("en")

    await query.answer(_("language_changed_en"))

    # Возвращаемся в меню профиля
    profile_text = _(
        "profile_text",
        user_id=user_id,
        language="🇬🇧 English",
    )

    await edit_menu_with_image(
        event=query, text=profile_text, reply_markup=profile_menu()
    )
