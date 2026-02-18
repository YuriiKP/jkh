import io

import qrcode
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommandScopeDefault,
    BufferedInputFile,
    CallbackQuery,
    Message,
)
from keyboards import *
from loader import db_manage, dp, get_full_subscription_url, marzban_client
from locales import get_text as _
from models.user import UserResponse
from utils.marzban_api import MarzbanAPIError

from ..common import edit_menu_with_image


# Обработчик кнопки "Мой ключ"
@dp.callback_query(F.data == "my_key")
async def my_key_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    user_id = query.from_user.id

    async def message_no_keys():
        await edit_menu_with_image(
            event=query,
            text=_("my_kyes_no_key"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=btn_main_menu, callback_data="start")],
                ]
            ),
        )

    # Есть ли пользователь в marzban
    try:
        user_marz: UserResponse = await marzban_client.get_user(str(user_id))

        # Если юзер есть в marzban то триала уже не должно быть
        user_tg = await db_manage.get_user_by_id(user_id)
        if user_tg[7] == "true":
            await db_manage.update_user(user_id=user_id, trial="false")
    except MarzbanAPIError as e:
        if e.status == 404:
            await message_no_keys()
            return
        print(e)

    text = my_keys_stat_info(user_marz)
    await edit_menu_with_image(
        event=query,
        text=text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=btn_how_to_connect, callback_data="how_to_connect"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=btn_get_qr_code, callback_data="get_qr_code"
                    )
                ],
                [InlineKeyboardButton(text=btn_main_menu, callback_data="start")],
            ]
        ),
    )


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
                event=query,
                text="Ключ не найден.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=btn_main_menu, callback_data="start"
                            )
                        ],
                    ]
                ),
            )
            return
        print(e)
        await query.answer("Ошибка при получении данных.")
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
        caption="Отсканируйте QR-код для подключения к VPN.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=btn_how_to_connect, callback_data="how_to_connect"
                    )
                ],
                [InlineKeyboardButton(text=btn_main_menu, callback_data="start")],
            ]
        ),
    )

    await query.answer("QR-код отправлен")
