"""
Модуль выдачи и продления подписок.

Единая точка входа для всех сценариев предоставления доступа
(оплата через ЮKassa, активация диплинка, пробный период).

Зачем нужен отдельный модуль:
- после оплаты/продления пользователь обязан оказаться в группе Pasarguard,
  иначе у него нет доступа к сервису, хотя он заплатил;
- логика выдачи/продления одна и та же — не должна дублироваться в хендлерах.

Как добавлять новые группы/тарифы:
- группа создаётся в панели Pasarguard (или через MarzbanAPIClient.create_group);
- сам тариф и его группа описываются в telegram/tariffs.py (TARIFFS).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from models.group import GroupResponse
from models.proxy import ProxyTable, VlessSettings, XTLSFlows
from models.user import (
    UserCreate,
    UserModify,
    UserResponse,
    UserStatusCreate,
    UserStatusModify,
)
from tariffs import DEFAULT_GROUP_NAME, get_tariff

from utils.marzban_api import MarzbanAPIClient, MarzbanAPIError

logger = logging.getLogger(__name__)


class SubscriptionError(Exception):
    """Ошибка при выдаче или продлении подписки."""


def _to_naive_datetime(value: datetime | int | None) -> datetime:
    """Приводит expire из панели (unix-время или datetime) к naive datetime."""
    if not value:
        return datetime.now()

    result = datetime.fromtimestamp(value) if isinstance(value, int) else value
    if result.tzinfo is not None:
        result = result.replace(tzinfo=None)
    return result


class SubscriptionService:
    """
    Выдаёт и продлевает доступ пользователя в панели Pasarguard.

    Гарантирует, что после вызова `grant` пользователь:
    - существует в панели и активен;
    - находится в нужной группе (а значит, имеет доступ к сервису);
    - имеет срок подписки, продлённый на запрошенное число дней.
    """

    def __init__(
        self,
        client: MarzbanAPIClient,
        *,
        default_group_name: str = DEFAULT_GROUP_NAME,
    ) -> None:
        self._client: MarzbanAPIClient = client
        self._default_group_name: str = default_group_name
        # Кэш «имя группы -> id», чтобы не дёргать API на каждую оплату.
        self._group_id_cache: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Группы
    # ------------------------------------------------------------------

    def group_name_for_tariff(self, tariff_key: str | None) -> str:
        """Возвращает имя группы для тарифа (или группу по умолчанию)."""
        return get_tariff(tariff_key).group or self._default_group_name

    async def resolve_group_id(self, group_name: str | None = None) -> int:
        """
        Возвращает id группы по имени.

        Если группы нет — выбрасывает SubscriptionError, чтобы ошибка
        в конфигурации не осталась незамеченной.
        """
        name = group_name or self._default_group_name
        cached = self._group_id_cache.get(name)
        if cached is not None:
            return cached

        group = await self._find_group_by_name(name)
        if group is None:
            raise SubscriptionError(
                f"Группа '{name}' не найдена в Pasarguard. Создайте её в панели или проверьте значение DEFAULT_GROUP_NAME."
            )

        self._group_id_cache[name] = group.id
        return group.id

    async def _find_group_by_name(self, name: str) -> GroupResponse | None:
        """Ищет группу по имени, перебирая страницы списка групп."""
        offset = 0
        limit = 100
        while True:
            page = await self._client.list_groups(offset=offset, limit=limit)
            for group in page.groups:
                if group.name == name:
                    return group

            offset += limit
            if not page.groups or offset >= page.total:
                return None

    # ------------------------------------------------------------------
    # Подписка
    # ------------------------------------------------------------------

    async def grant(
        self,
        user_id: int,
        *,
        days: int,
        tariff: str | None = None,
        group_name: str | None = None,
        note: str | None = None,
    ) -> UserResponse:
        """
        Выдаёт или продлевает подписку пользователя на `days` дней.

        :param days: сколько дней добавить (для нового пользователя — срок подписки).
        :param tariff: ключ тарифа; по нему определяется группа (если group_name не задан).
        :param group_name: явное имя группы (приоритетнее tariff).
        :param note: заметка для нового пользователя.
        """
        if days <= 0:
            raise SubscriptionError("Количество дней подписки должно быть больше нуля")

        target_group_name = group_name or self.group_name_for_tariff(tariff)
        group_id = await self.resolve_group_id(target_group_name)

        try:
            user = await self._client.get_user(str(user_id))
        except MarzbanAPIError as e:
            if e.status != 404:
                raise
            user = None

        if user is None:
            return await self._create_user(user_id, days, group_id, note)

        return await self._extend_user(user, days, group_id)

    async def _create_user(
        self,
        user_id: int,
        days: int,
        group_id: int,
        note: str | None,
    ) -> UserResponse:
        new_user = UserCreate(
            username=str(user_id),
            note=note or f"User {user_id}",
            status=UserStatusCreate.active,
            expire=datetime.now() + timedelta(days=days),
            group_ids=[group_id],
            proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION)),
        )
        user = await self._client.create_user(new_user)
        self._verify_group(user, group_id)
        return user

    async def _extend_user(
        self,
        user: UserResponse,
        days: int,
        group_id: int,
    ) -> UserResponse:
        new_expire = _to_naive_datetime(user.expire) + timedelta(days=days)
        group_ids = self._merge_group_ids(user.group_ids, group_id)

        update = UserModify(
            expire=new_expire,
            group_ids=group_ids,
            proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION)),
            status=UserStatusModify.active,
        )
        modified = await self._client.modify_user(user.username, update)
        self._verify_group(modified, group_id)
        return modified

    # ------------------------------------------------------------------
    # Вспомогательное
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_group_ids(existing: list[int] | None, group_id: int) -> list[int]:
        """Добавляет группу к уже имеющимся у пользователя, сохраняя остальные."""
        group_ids = list(existing) if existing else []
        if group_id not in group_ids:
            group_ids.append(group_id)
        return group_ids

    @staticmethod
    def _verify_group(user: UserResponse, group_id: int) -> None:
        """Логирует предупреждение, если пользователь всё же остался без нужной группы."""
        group_ids = user.group_ids or []
        if group_id not in group_ids:
            logger.warning(
                "Пользователь %s не попал в группу %s (group_ids=%s)",
                user.username,
                group_id,
                group_ids,
            )
