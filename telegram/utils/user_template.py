"""
Применение «шаблона пользователя» Pasarguard после окончания подписки.

Когда срок подписки заканчивается, панель присылает в бот webhook
с действием `user_expired`. В ответ бот применяет к пользователю
заранее настроенный шаблон.

Почему именно «изменить по шаблону», а не «создать заново»:
- в Pasarguard username уникален, поэтому создать второго пользователя
  с тем же именем нельзя — панель вернёт ошибку 409 Conflict;
- штатная операция «применить шаблон» — это `PUT /api/user/from_template/{username}`
  (Modify User With Template): имя пользователя не меняется, а срок/лимит/группы
  берутся из шаблона. Именно это делает кнопка «применить шаблон» в панели;
- если пользователя в панели вдруг нет — он создаётся из шаблона
  (`POST /api/user/from_template`).

Шаблон задаётся именем через переменную окружения `EXPIRED_TEMPLATE_NAME`.
Если она не задана — применение шаблона выключено.
"""

from __future__ import annotations

import logging

from models.user import UserResponse

from utils.marzban_api import MarzbanAPIClient, MarzbanAPIError

logger = logging.getLogger(__name__)


class UserTemplateError(Exception):
    """Ошибка при применении шаблона пользователя."""


class UserTemplateService:
    """
    Применяет шаблон пользователя Pasarguard к существующему пользователю.

    Шаблон задаётся именем (`template_name`); имя разрешается в id через
    `GET /api/user_templates` и кэшируется.
    """

    def __init__(
        self,
        client: MarzbanAPIClient,
        *,
        template_name: str | None = None,
    ) -> None:
        self._client: MarzbanAPIClient = client
        self._template_name: str | None = (template_name or "").strip() or None
        self._resolved_id: int | None = None

    @property
    def enabled(self) -> bool:
        """Включено ли применение шаблона (задано имя шаблона)."""
        return self._template_name is not None

    async def resolve_template_id(self) -> int:
        """Возвращает id шаблона, разрешая его по имени."""
        if not self._template_name:
            raise UserTemplateError("Не задан EXPIRED_TEMPLATE_NAME")

        if self._resolved_id is not None:
            return self._resolved_id

        templates = await self._client.list_user_templates()
        for template in templates:
            if template.name == self._template_name:
                self._resolved_id = template.id
                return template.id

        raise UserTemplateError(
            f"Шаблон '{self._template_name}' не найден в Pasarguard. Создайте его в панели или поправьте EXPIRED_TEMPLATE_NAME."
        )

    async def apply(self, username: str) -> UserResponse:
        """
        Применяет шаблон к пользователю `username`.

        Сначала пытается изменить существующего пользователя по шаблону,
        а если такого пользователя нет — создаёт его из шаблона.
        """
        template_id = await self.resolve_template_id()

        try:
            return await self._client.modify_user_with_template(
                username, user_template_id=template_id
            )
        except MarzbanAPIError as e:
            if e.status != 404:
                raise
            logger.info(
                "Пользователь %s не найден в панели — создаём из шаблона %s",
                username,
                template_id,
            )

        return await self._client.create_user_from_template(
            username, user_template_id=template_id
        )
