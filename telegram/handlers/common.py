import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    Message,
)
from keyboards import *
from loader import (
    bot,
    load_menu_image,
)

logger = logging.getLogger(__name__)


# Функция для редактирования меню с изображением
async def edit_menu_with_image(
    event: Message | CallbackQuery, text: str, reply_markup=None
):
    """
    Редактирует меню как подпись к изображению.
    """
    if isinstance(event, CallbackQuery):
        # Проверяем, что сообщение существует и это не InaccessibleMessage
        if event.message and isinstance(event.message, Message):
            event = event.message
        else:
            # Если сообщение недоступно, редактировать его нельзя
            logger.error("Сообщение недоступно")
            return

    try:
        # Пытаемся отредактировать подпись к изображению
        await event.edit_caption(
            caption=text, reply_markup=reply_markup, parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        # Если нельзя редактировать (например, сообщение не содержит изображение),
        # отправляем новое сообщение и удаляем старое
        logger.warning(
            f"Нельзя редактировать сообщение: {e}. Отправляем новое сообщение."
        )

        try:
            # Загружаем или получаем file_id изображения меню
            menu_image_id = await load_menu_image()

            if menu_image_id:
                # Отправляем новое изображение с подписью
                await bot.send_photo(
                    chat_id=event.chat.id,
                    photo=menu_image_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            else:
                # Если не удалось загрузить изображение, отправляем обычное сообщение
                await bot.send_message(
                    chat_id=event.chat.id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )

            # Пытаемся удалить старое сообщение
            try:
                if isinstance(event, Message) and not event.text.startswith("/"):
                    await event.delete()
            except TelegramBadRequest:
                pass  # Игнорируем, если уже удалено

        except Exception as e:
            logging.error(f"Ошибка отправки нового сообщения с меню: {e}")
            # Fallback: отправляем обычное сообщение
            await bot.send_message(
                chat_id=event.chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
