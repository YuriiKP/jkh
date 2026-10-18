import asyncio
import logging

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
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

# Максимальная пауза перед повтором запроса при флуд-контроле Telegram.
MAX_RETRY_AFTER = 30

# Ошибки Telegram, при которых меню нужно отправить заново, а не редактировать.
NETWORK_ERRORS = (TelegramNetworkError, TelegramServerError)


async def _edit_caption(message: Message, text: str, reply_markup) -> bool:
    """
    Пытается отредактировать подпись к изображению.

    Возвращает True при успехе. Любая ошибка Telegram здесь не пробрасывается:
    вызывающий код в этом случае просто отправит новое сообщение.
    """
    try:
        await message.edit_caption(
            caption=text, reply_markup=reply_markup, parse_mode="HTML"
        )
        return True
    except TelegramRetryAfter as e:
        # Telegram просит подождать — ждём (но не дольше разумного) и пробуем ещё раз
        delay = min(e.retry_after, MAX_RETRY_AFTER)
        logger.warning(
            f"Флуд-контроль Telegram при редактировании меню, "
            f"повтор через {delay} с: {e}"
        )
        await asyncio.sleep(delay)
        try:
            await message.edit_caption(
                caption=text, reply_markup=reply_markup, parse_mode="HTML"
            )
            return True
        except (TelegramBadRequest, *NETWORK_ERRORS) as retry_error:
            logger.warning(
                f"Повторное редактирование меню не удалось: "
                f"{type(retry_error).__name__}: {retry_error}"
            )
            return False
    except TelegramBadRequest as e:
        # Например, сообщение не содержит изображение — отредактировать нельзя
        logger.warning(
            f"Нельзя отредактировать сообщение: {e}. Отправляем новое сообщение."
        )
        return False
    except NETWORK_ERRORS as e:
        # Таймаут/обрыв связи с Telegram: раньше это исключение не ловилось,
        # обработчик падал целиком и пользователь не видел ответа вообще.
        logger.error(
            f"Сетевая ошибка Telegram при редактировании меню: {type(e).__name__}: {e}"
        )
        return False


async def _delete_old_message(message: Message) -> None:
    """
    Пытается удалить старое сообщение меню. Ошибки удаления не критичны.
    """
    # message.text может быть None (сообщение с фото), поэтому проверяем аккуратно,
    # иначе None.startswith() роняет обработчик.
    text = message.text or message.caption or ""
    if text.startswith("/"):
        return

    try:
        await message.delete()
    except (TelegramBadRequest, *NETWORK_ERRORS) as e:
        logger.debug(f"Не удалось удалить старое меню: {type(e).__name__}: {e}")


async def _send_new_menu(message: Message, text: str, reply_markup) -> bool:
    """
    Отправляет меню новым сообщением (с изображением, если оно доступно).
    """
    try:
        menu_image_id = await load_menu_image()
    except Exception as e:
        logger.error(f"Ошибка получения изображения меню: {e}")
        menu_image_id = None

    if menu_image_id:
        try:
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=menu_image_id,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            # Старое сообщение удаляем только после успешной отправки нового
            await _delete_old_message(message)
            return True
        except (TelegramBadRequest, *NETWORK_ERRORS) as e:
            # Например, file_id изображения устарел — уходим в обычный текст
            logger.warning(
                f"Не удалось отправить меню с изображением: "
                f"{type(e).__name__}: {e}. Отправляем текстом."
            )

    try:
        await bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except (TelegramBadRequest, *NETWORK_ERRORS) as e:
        logger.error(
            f"Ошибка отправки нового сообщения с меню: {type(e).__name__}: {e}"
        )
        return False

    # Старое сообщение удаляем только после успешной отправки нового
    await _delete_old_message(message)
    return True


# Функция для редактирования меню с изображением
async def edit_menu_with_image(
    event: Message | CallbackQuery, text: str, reply_markup=None
):
    """
    Редактирует меню как подпись к изображению.

    Если отредактировать сообщение нельзя (нет фото, сообщение недоступно,
    сетевой сбой Telegram) — отправляет меню новым сообщением.
    """
    if isinstance(event, CallbackQuery):
        # Проверяем, что сообщение существует и это не InaccessibleMessage
        if event.message and isinstance(event.message, Message):
            event = event.message
        else:
            # Если сообщение недоступно, редактировать его нельзя
            logger.error("Сообщение недоступно")
            return

    if await _edit_caption(event, text, reply_markup):
        return

    await _send_new_menu(event, text, reply_markup)
