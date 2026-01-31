import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    Message,
)
from keyboards import *
from loader import (
    MENU_IMAGE,
    bot,
    load_menu_image,
)

logger = logging.getLogger(__name__)


# Функция отправки меню с изображением
async def send_menu_with_image(chat_id: int, text: str, reply_markup=None):
    """
    Отправляет меню как подпись к изображению.
    """
    try:
        # Загружаем или получаем file_id изображения меню
        menu_image_id = await load_menu_image()

        if menu_image_id:
            # Отправляем изображение с подписью (меню)
            await bot.send_photo(
                chat_id=chat_id,
                photo=menu_image_id,
                caption=text,
                reply_markup=reply_markup,
            )
        else:
            # Если не удалось загрузить изображение, отправляем обычное сообщение
            await bot.send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML"
            )
    except Exception as e:
        logging.error(f"Error sending menu with image: {e}")
        # Fallback: отправляем обычное сообщение
        await bot.send_message(
            chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML"
        )


# Функция для редактирования меню
async def edit_menu_with_image(event: Message | CallbackQuery, reply_markup=None):
    """
    Редактирует меню как подпись к изображению.
    """

    if isinstance(event, CallbackQuery):
        # Проверяем, что сообщение существует и это не InaccessibleMessage
        if event.message and isinstance(event.message, Message):
            event = event.message
        else:
            # Если сообщение недоступно, редактировать его нельзя
            logger.error("Message is inaccessible")
            return

    try:
        await event.edit_caption(text=user_buy_text, reply_markup=buy_menu())
    except TelegramBadRequest:
        # Если нельзя редактировать, отправляем новое сообщение и удаляем старое
        await event.answer_photo(
            photo=MENU_IMAGE, text=user_buy_text, reply_markup=buy_menu()
        )
        try:
            if event.text and not event.text.startswith("/"):
                await event.delete()
        except TelegramBadRequest:
            pass
