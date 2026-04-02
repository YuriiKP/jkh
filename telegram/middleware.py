import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from locales import Locales, setup_context
from locales import get_text as _
from storage import DB_M

logger = logging.getLogger(__name__)


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
        user_id = data["event_chat"].id
        user_info = await self.db_manage.get_user_by_id(user_id)

        # Дефолтный язык
        # Определяем язык по умолчанию
        lang = "en"
        # Определяем язык: сначала из базы, если есть, иначе из Телеграм
        lang_source = (
            str(user_info[6]) if user_info else data["event_from_user"].language_code
        )
        if lang_source in ("ru", "en", "fa"):
            lang = lang_source

        # print("Язык интерфейса:", data["event_from_user"].language_code)
        # print("Язык из базы данных:", lang_source)

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

        # Проверяем статус пользователя, если админ - пропускаем
        user_id = data["event_chat"].id
        status_user = await self.db_manage.get_status_user(user_id)

        if status_user and status_user[0] in ("admin", "main_admin"):
            return await handler(event, data)

        # Если пользователь не админ, отправляем сообщение о тех. работах
        try:
            if event.message is not None:
                await event.message.answer(text=_("bot_under_maintenance"))
            elif event.callback_query is not None:
                await event.callback_query.answer(
                    text=_("bot_under_maintenance_alert"), show_alert=True
                )
        except Exception as e:
            logger.error(
                f"Ошибка при отправке сообщения о техническом обслуживании: {e}"
            )

        # Прерываем обработку для обычных пользователей
        return
