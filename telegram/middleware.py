from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from locales import Locales, setup_context
from storage import DB_M


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
        if lang_source in ("ru", "en"):
            lang = lang_source

        print("Язык интерфейса:", data["event_from_user"].language_code)
        print("Язык из базы данных:", lang_source)

        # Добавляем в data
        data["lang"] = lang
        data["locales"] = self.locales

        setup_context(self.locales, lang)

        return await handler(event, data)
