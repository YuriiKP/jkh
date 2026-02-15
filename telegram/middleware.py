from typing import Any

from aiogram.types import TelegramObject
from storage import DB_M


class MyI18nMiddleware(I18nMiddleware):
    """
    Const middleware chooses statically defined locale
    """

    def __init__(
        self,
        i18n: I18n,
        i18n_key: str | None = "i18n",
        middleware_key: str = "i18n_middleware",
        db_manage: DB_M = None,
    ) -> None:
        super().__init__(i18n=i18n, i18n_key=i18n_key, middleware_key=middleware_key)
        self.db_manage = db_manage

    async def get_locale(self, event: TelegramObject, data: dict[str, Any]) -> str:
        user_info = await self.db_manage.get_user_by_id(user_id=data["event_chat"].id)

        if user_info is None:
            return "en"

        locate_from_db = user_info[6]
        print(locate_from_db)

        if locate_from_db and locate_from_db in ("ru", "en"):
            return locate_from_db
        else:
            return "en"
