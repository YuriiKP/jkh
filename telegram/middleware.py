import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from locales import Locales, setup_context
from locales import get_text as _
from storage import DB_M

logger = logging.getLogger(__name__)


def _get_user_id(data: Dict[str, Any]) -> int | None:
    """
    Возвращает id пользователя из апдейта.

    Часть апдейтов не содержит чат (например, `pre_checkout_query`),
    поэтому берём пользователя из `event_context`/`event_from_user`,
    а не из `event_chat`, иначе получаем KeyError.
    """
    context = data.get("event_context")
    if context is not None and getattr(context, "user_id", None) is not None:
        return context.user_id

    user = data.get("event_from_user")
    if user is not None:
        return user.id

    chat = data.get("event_chat")
    if chat is not None:
        return chat.id

    return None


class MyLocalesMiddleware(BaseMiddleware):
    """
    Middleware, который выбирает язык
    """

    def __init__(self, locales: Locales, db_manage: DB_M):
        self.locales = locales
        self.db_manage = db_manage

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event,
        data: Dict[str, Any],
    ):
        user_id = _get_user_id(data)

        user_info = None
        if user_id is not None:
            user_info = await self.db_manage.get_user_by_id(user_id)

        # Определяем язык: сначала из базы, иначе из Telegram
        lang_source = None
        if user_info:
            lang_source = str(user_info[6])
        else:
            from_user = data.get("event_from_user")
            lang_source = getattr(from_user, "language_code", None)

        # Дефолтный язык
        lang = "en"
        if lang_source in ("ru", "en", "fa"):
            lang = lang_source

        # Добавляем в data
        data["lang"] = lang
        data["locales"] = self.locales

        setup_context(self.locales, lang)

        return await handler(event, data)


class DebugModeMiddleware(BaseMiddleware):
    """
    Middleware для проверки режима отладки.
    Если DEBUG=True, то доступ к боту имеют только администраторы.
    Обычные пользователи получают сообщение о технических работах.
    """

    def __init__(self, db_manage: DB_M):
        self.db_manage = db_manage

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event,
        data: Dict[str, Any],
    ):
        user_id = _get_user_id(data)

        # Не удалось определить пользователя — пропускаем апдейт дальше
        if user_id is None:
            return await handler(event, data)

        # Проверяем статус пользователя, если админ - пропускаем
        status_user = await self.db_manage.get_status_user(user_id)

        if status_user and status_user[0] in ("admin", "main_admin"):
            return await handler(event, data)

        # Если пользователь не админ, отправляем сообщение о тех. работах
        try:
            if getattr(event, "message", None) is not None:
                await event.message.answer(text=_("bot_under_maintenance"))
            elif getattr(event, "callback_query", None) is not None:
                await event.callback_query.answer(
                    text=_("bot_under_maintenance_alert"), show_alert=True
                )
        except Exception as e:
            logger.error(
                f"Ошибка при отправке сообщения о техническом обслуживании: {e}"
            )

        # Прерываем обработку для обычных пользователей
        return
