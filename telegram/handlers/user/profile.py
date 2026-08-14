import html
import io
from datetime import datetime

import qrcode
import qrcode.constants
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery
from keyboards import *
from loader import db_manage, dp, get_full_subscription_url, marzban_client
from locales import get_text as _
from locales import update_lang
from models.user import UserResponse
from utils.marzban_api import MarzbanAPIError

from ..common import edit_menu_with_image


def _lang_display(lang: str) -> str:
    """Возвращает отображаемое название языка."""
    if lang == "ru":
        return "🇷🇺 Русский"
    if lang == "fa":
        return "🇮🇷 فارسی"
    return "🇬🇧 English"


def _status_emoji(status: str) -> str:
    """Возвращает эмодзи для статуса подписки."""
    status_emoji = {
        "active": "✅",
        "disabled": "❌",
        "limited": "⚠️",
        "expired": "⏰",
        "on_hold": "⏸️",
    }
    return status_emoji.get(status, "❓")


def _expire_text(expire) -> str:
    """Форматирует дату окончания подписки."""
    if expire == 0:
        return "∞"
    if expire is not None:
        # Обрабатываем expire как datetime или timestamp (int)
        if isinstance(expire, int):
            expire_date = datetime.fromtimestamp(expire)
        else:
            expire_date = expire
            # Если datetime имеет timezone, конвертируем в naive datetime для сравнения
            if expire_date.tzinfo is not None:
                expire_date = expire_date.replace(tzinfo=None)

        # Вычисляем оставшиеся дни (используем naive datetime для сравнения)
        now = datetime.now()
        remaining_days = (expire_date - now).days

        # Форматируем дату и оставшиеся дни
        return expire_date.strftime("%d.%m.%y | ") + f" ({remaining_days} д.)"
    return "На паузе"


async def get_marzban_user(user_id: int) -> UserResponse | None:
    """
    Возвращает пользователя Marzban по Telegram user_id.

    Если пользователь найден — снимает флаг trial в БД.
    Если пользователя нет (404) или произошла ошибка API — возвращает None.
    """
    try:
        user_marz: UserResponse = await marzban_client.get_user(str(user_id))
    except MarzbanAPIError as e:
        if e.status == 404:
            return None
        print(e)
        return None

    # Если юзер есть в marzban — триала уже не должно быть
    user_tg = await db_manage.get_user_by_id(user_id)
    if user_tg is not None and str(user_tg[7]) == "true":
        await db_manage.update_user(user_id=user_id, trial="false")

    return user_marz


async def build_profile_text(
    user_id: int, language: str, user_marz: UserResponse | None = None
) -> str:
    """Формирует текст профиля (с информацией о ключе или без неё)."""
    if user_marz is None:
        user_marz = await get_marzban_user(user_id)

    if user_marz is None:
        return _("profile_text_no_key", user_id=user_id, language=language)

    # Экранируем URL перед вставкой в <code>-блок шаблона
    # (Telegram показывает кнопку «Копировать» при нажатии на код)
    full_subscription_url = html.escape(
        get_full_subscription_url(user_marz.subscription_url), quote=True
    )

    return _(
        "profile_text",
        user_id=user_id,
        language=language,
        emoji=_status_emoji(user_marz.status.value),
        status=_(user_marz.status.value),
        lifetime_used_gb=user_marz.lifetime_used_traffic / (1024**3),
        expire_text=_expire_text(user_marz.expire),
        full_subscription_url=full_subscription_url,
    )


# Обработчик кнопки "Профиль"
@dp.callback_query(F.data == "btn_profile")
async def profile_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    user_id = query.from_user.id
    user = await db_manage.get_user_by_id(user_id)
    if user is None:
        return

    current_lang = str(user[6])  # language находится на 6-й позиции (индекс 6)
    lang_display = _lang_display(current_lang)

    user_marz = await get_marzban_user(user_id)
    profile_text = await build_profile_text(user_id, lang_display, user_marz)

    subscription_url = (
        get_full_subscription_url(user_marz.subscription_url)
        if user_marz is not None
        else None
    )

    await edit_menu_with_image(
        event=query, text=profile_text, reply_markup=profile_menu(subscription_url)
    )


# Обработчик кнопки "Язык"
@dp.callback_query(F.data == "language")
async def language_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    language_text = _("language_selection_text")

    await edit_menu_with_image(
        event=query, text=language_text, reply_markup=language_menu()
    )


async def _lang_changed(
    query: CallbackQuery, lang: str, lang_display: str, notice_key: str
):
    """Общая логика после смены языка: сохраняем язык и показываем профиль."""
    user_id = query.from_user.id
    await db_manage.update_user(user_id=user_id, language=lang)

    # Обновляем контекст языка
    update_lang(lang)

    await query.answer(_(notice_key))

    # Возвращаемся в меню профиля (с информацией о ключе)
    user_marz = await get_marzban_user(user_id)
    profile_text = await build_profile_text(user_id, lang_display, user_marz)

    subscription_url = (
        get_full_subscription_url(user_marz.subscription_url)
        if user_marz is not None
        else None
    )

    await edit_menu_with_image(
        event=query, text=profile_text, reply_markup=profile_menu(subscription_url)
    )


# Обработчик выбора русского языка
@dp.callback_query(F.data == "btn_lang_ru")
async def lang_ru_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await _lang_changed(query, "ru", "🇷🇺 Русский", "language_changed_ru")


# Обработчик выбора английского языка
@dp.callback_query(F.data == "btn_lang_en")
async def lang_en_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await _lang_changed(query, "en", "🇬🇧 English", "language_changed_en")


# Обработчик выбора персидского языка
@dp.callback_query(F.data == "btn_lang_fa")
async def lang_fa_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await _lang_changed(query, "fa", "🇮🇷 فارسی", "language_changed_fa")


# Обработчик кнопки "Получить QR-код"
@dp.callback_query(F.data == "get_qr_code")
async def get_qr_code_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    user_id = query.from_user.id

    try:
        user_marz: UserResponse = await marzban_client.get_user(str(user_id))
    except MarzbanAPIError as e:
        if e.status == 404:
            await edit_menu_with_image(
                event=query, text=_("my_kyes_no_key"), reply_markup=user_btn_main_menu()
            )
            return
        print(e)
        await query.answer(_("my_keys_error_get_data"))
        return

    if query.message is None:
        return

    # Генерация QR-кода из subscription_url
    full_subscription_url = get_full_subscription_url(user_marz.subscription_url)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(full_subscription_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Сохраняем в буфер
    buffer = io.BytesIO()
    img.save(buffer, "PNG")
    buffer.seek(0)

    # Отправляем QR-код как фото
    await query.message.reply_photo(
        photo=BufferedInputFile(buffer.getvalue(), filename="qr_code.png"),
    )
    # Отправляем текст отдельным сообщением
    await query.message.answer(
        text=_("my_keys_qr_code"),
        reply_markup=user_qr_code_menu(),
    )

    await query.answer(_("my_keys_qr_notice"))
