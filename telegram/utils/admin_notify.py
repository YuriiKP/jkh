"""
Уведомление главного администратора о покупке.

Отправляет главному админу простое сообщение на русском: кто что купил.
"""

import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from loader import TG_ADMIN, bot

logger = logging.getLogger(__name__)


async def notify_admin_about_purchase(
    user_id: int,
    product: str,
    first_name: str | None = None,
    username: str | None = None,
) -> None:
    """
    Сообщает главному админу о покупке.

    :param user_id: id покупателя в Telegram.
    :param product: что куплено (например, «1 месяц»).
    :param first_name: имя покупателя.
    :param username: username покупателя (без @).
    """
    if not TG_ADMIN:
        return

    name = first_name or "Пользователь"
    if username:
        name += f" (@{username})"

    text = f"💰 {name} (ID: {user_id}) купил {product}."

    try:
        await bot.send_message(chat_id=TG_ADMIN, text=text)
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.error(f"Не удалось уведомить главного админа о покупке: {e}")
