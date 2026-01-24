import asyncio
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import ClientResponse
import ssl

# Важно: здесь используются абсолютные импорты относительно пакета `telegram`,
# чтобы модуль корректно работал при запуске скрипта `telegram/main.py`.
from models.admin import Admin, AdminCreate, AdminModify, Token
from models.user import (
    UserCreate,
    UserModify,
    UserResponse,
    UsersResponse,
    UserUsagesResponse,
    UsersUsagesResponse,
)
from models.user_template import (
    UserTemplateCreate,
    UserTemplateModify,
    UserTemplateResponse,
)
from models.node import (
    NodeCreate,
    NodeModify,
    NodeResponse,
    NodesUsageResponse,
)
from models.system import SystemStats


class MarzbanAPIError(Exception):
    """Базовое исключение для ошибок при работе с Marzban API."""

    def __init__(self, status: int, message: str, payload: Any | None = None):
        self.status = status
        self.message = message
        self.payload = payload
        super().__init__(f"Marzban API error {status}: {message}")


class MarzbanAPIClient:
    """
    Асинхронный клиент для Marzban API на базе aiohttp.

    Использует pydantic‑модели из пакета `telegram.models` для сериализации /
    десериализации запросов и ответов.
    """

    def __init__(
        self,
        base_url: str,
        *,
        admin_username: str,
        admin_password: str,
        session: aiohttp.ClientSession | None = None,
        request_timeout: int = 15,
    ) -> None:
        """
        :param base_url: Базовый URL панели Marzban, например: "http://127.0.0.1:8000"
                         (без завершающего слеша).
        :param admin_username: Логин админа для аутентификации.
        :param admin_password: Пароль админа для аутентификации.
        :param session: Необязательная внешняя aiohttp‑сессия
                        (если не указана – будет создана внутренняя).
        :param request_timeout: Таймаут HTTP‑запросов, секунд.
        """
        self._base_url = base_url.rstrip("/")
        self._admin_username = admin_username
        self._admin_password = admin_password
        self._external_session = session
        self._session: aiohttp.ClientSession | None = session
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._access_token: str | None = None

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    @property
    def access_token(self) -> str | None:
        """Текущий токен администратора (может быть None, если ещё не авторизовались)."""
        return self._access_token

    async def _get_session(self) -> aiohttp.ClientSession:
        """Ленивая инициализация aiohttp‑сессии."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            
            # Временно отключаем проверку SSL для обхода проблем с сертификатами
            # connector = aiohttp.TCPConnector(verify_ssl=False)
            # self._session = aiohttp.ClientSession(timeout=self._timeout, connector=connector)
        return self._session

    async def close(self) -> None:
        """Закрыть внутреннюю HTTP‑сессию (если она была создана клиентом)."""
        if self._session is not None and self._session is not self._external_session:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> "MarzbanAPIClient":
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    def _auth_headers(self) -> Dict[str, str]:
        """Сформировать заголовки авторизации, если токен установлен."""
        headers: Dict[str, str] = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def _raise_for_status(self, resp: ClientResponse) -> None:
        """Преобразование неуспешных ответов API в MarzbanAPIError с телом ответа."""
        if 200 <= resp.status < 300:
            return
        try:
            data = await resp.json()
        except Exception:
            text = await resp.text()
            raise MarzbanAPIError(resp.status, text)

        message = data.get("detail") if isinstance(data, dict) else str(data)
        raise MarzbanAPIError(resp.status, message, payload=data)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Dict[str, Any] | None = None,
        json: Any | None = None,
        data: Any | None = None,
        need_auth: bool = True,
    ) -> Any:
        """
        Унифицированный метод отправки HTTP‑запроса с автоматической повторной аутентификацией при 401 ошибке.

        :param method: HTTP‑метод (GET, POST, PUT, DELETE ...).
        :param path: Путь внутри API, например "/api/admin".
        :param params: Параметры query‑строки.
        :param json: JSON‑тело запроса.
        :param data: Форм‑данные (используется для /api/admin/token).
        :param need_auth: Требуется ли заголовок Authorization.
        """
        session = await self._get_session()

        # Автоматическая аутентификация: если необходимо
        if need_auth and not self._access_token:
            await self._authenticate()

        url = f"{self._base_url}{path}"
        headers: Dict[str, str] = {}
        if need_auth:
            headers.update(self._auth_headers())

        async def _make_request() -> Any:
            async with session.request(
                method,
                url,
                params=params,
                json=json,
                data=data,
                headers=headers,
            ) as resp:
                await self._raise_for_status(resp)
                # Пытаемся распарсить JSON, пустой ответ вернёт None / ""
                if resp.content_type == "application/json":
                    return await resp.json()
                text = await resp.text()
                return text

        try:
            return await _make_request()
        except MarzbanAPIError as e:
            # Если получен код 401 и требуется авторизация, выполняем повторную аутентификацию
            if e.status == 401 and need_auth:
                await self._authenticate()
                headers.update(self._auth_headers())
                return await _make_request()
            else:
                raise

    # ------------------------------------------------------------------
    # Аутентификация администратора
    # ------------------------------------------------------------------

    async def _authenticate(self) -> None:
            """Выполнить аутентификацию администратора и сохранить токен."""
            form_data: Dict[str, str] = {
                "grant_type": "password",
                "username": self._admin_username,
                "password": self._admin_password,
            }
            
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/api/admin/token",
                data=form_data,
            ) as resp_token:
                await self._raise_for_status(resp_token)
                data_token = await resp_token.json()
                token = Token.model_validate(data_token)
                self._access_token = token.access_token

    # ------------------------------------------------------------------
    # Admin API
    # ------------------------------------------------------------------

    async def get_current_admin(self) -> Admin:
        """GET /api/admin — получить текущего аутентифицированного админа."""
        data = await self._request("GET", "/api/admin")
        return Admin.model_validate(data)

    async def create_admin(self, admin: AdminCreate) -> Admin:
        """POST /api/admin — создать нового администратора (нужны sudo‑права)."""
        payload = admin.model_dump(exclude_none=True)
        data = await self._request("POST", "/api/admin", json=payload)
        return Admin.model_validate(data)

    async def modify_admin(self, username: str, update: AdminModify) -> Admin:
        """PUT /api/admin/{username} — изменить данные администратора."""
        payload = update.model_dump(exclude_none=True)
        data = await self._request("PUT", f"/api/admin/{username}", json=payload)
        return Admin.model_validate(data)

    async def delete_admin(self, username: str) -> str:
        """
        DELETE /api/admin/{username} — удалить администратора.

        Маршрут по Swagger возвращает строку (обычно сообщение об удалении).
        """
        data = await self._request("DELETE", f"/api/admin/{username}")
        # Если ответ JSON - это строка, просто возвращаем её
        return str(data)

    async def list_admins(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
        username: str | None = None,
    ) -> Dict[str, Any]:
        """
        GET /api/admins — список админов с фильтрами.

        Структура ответа в Swagger довольно объёмная, поэтому здесь возвращается
        сырой dict. При необходимости можно обернуть в собственную pydantic‑модель.
        """
        params: Dict[str, Any] = {}
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        if username:
            params["username"] = username

        data = await self._request("GET", "/api/admins", params=params)
        return data

    # ------------------------------------------------------------------
    # Users API
    # ------------------------------------------------------------------

    async def create_user(self, user: UserCreate) -> UserResponse:
        """POST /api/user — создать пользователя."""
        # Проверяем, существует ли пользователь уже
        try:
            existing_user = await self.get_user(user.username)
            return existing_user
        except MarzbanAPIError as e:
            if e.status == 404:
                payload = user.model_dump(exclude_none=True)
                data = await self._request("POST", "/api/user", json=payload)
                return UserResponse.model_validate(data)
            raise

    async def get_user(self, username: str) -> UserResponse:
        """GET /api/user/{username} — получить пользователя по username."""
        data = await self._request("GET", f"/api/user/{username}")
        return UserResponse.model_validate(data)

    async def modify_user(self, username: str, update: UserModify) -> UserResponse:
        """PUT /api/user/{username} — изменить пользователя."""
        payload = update.model_dump(exclude_none=True)
        data = await self._request("PUT", f"/api/user/{username}", json=payload)
        return UserResponse.model_validate(data)

    async def delete_user(self, username: str) -> str:
        """DELETE /api/user/{username} — удалить пользователя."""
        data = await self._request("DELETE", f"/api/user/{username}")
        return str(data)

    async def list_users(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
        username: str | None = None,
        status: str | None = None,
    ) -> UsersResponse:
        """
        GET /api/users — получить список пользователей.

        Тело ответа согласно Swagger маппится на модель UsersResponse.
        """
        params: Dict[str, Any] = {}
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        if username:
            params["username"] = username
        if status:
            params["status"] = status

        data = await self._request("GET", "/api/users", params=params)
        return UsersResponse.model_validate(data)

    async def get_user_usages(self, username: str) -> UserUsagesResponse:
        """
        GET /api/user/{username}/usages — трафик пользователя по нодам.
        """
        data = await self._request("GET", f"/api/user/{username}/usages")
        return UserUsagesResponse.model_validate(data)

    async def list_users_usages(self) -> UsersUsagesResponse:
        """
        GET /api/users/usages — сводная статистика трафика для всех пользователей.
        """
        data = await self._request("GET", "/api/users/usages")
        return UsersUsagesResponse.model_validate(data)

    # ------------------------------------------------------------------
    # User Templates API
    # ------------------------------------------------------------------

    async def create_user_template(
        self, template: UserTemplateCreate
    ) -> UserTemplateResponse:
        """POST /api/user_template — создать пользовательский шаблон."""
        payload = template.model_dump(exclude_none=True)
        data = await self._request("POST", "/api/user_template", json=payload)
        return UserTemplateResponse.model_validate(data)

    async def modify_user_template(
        self, template_id: int, update: UserTemplateModify
    ) -> UserTemplateResponse:
        """PUT /api/user_template/{id} — изменить пользовательский шаблон."""
        payload = update.model_dump(exclude_none=True)
        data = await self._request(
            "PUT", f"/api/user_template/{template_id}", json=payload
        )
        return UserTemplateResponse.model_validate(data)

    async def delete_user_template(self, template_id: int) -> str:
        """DELETE /api/user_template/{id} — удалить шаблон пользователя."""
        data = await self._request("DELETE", f"/api/user_template/{template_id}")
        return str(data)

    async def list_user_templates(self) -> List[UserTemplateResponse]:
        """GET /api/user_templates — список всех шаблонов пользователей."""
        data = await self._request("GET", "/api/user_templates")
        # Ожидаем список JSON‑объектов
        return [UserTemplateResponse.model_validate(item) for item in data]

    # ------------------------------------------------------------------
    # Nodes API
    # ------------------------------------------------------------------

    async def create_node(self, node: NodeCreate) -> NodeResponse:
        """POST /api/node — создать ноду."""
        payload = node.model_dump(exclude_none=True)
        data = await self._request("POST", "/api/node", json=payload)
        return NodeResponse.model_validate(data)

    async def modify_node(self, node_id: int, update: NodeModify) -> NodeResponse:
        """PUT /api/node/{id} — изменить ноду."""
        payload = update.model_dump(exclude_none=True)
        data = await self._request("PUT", f"/api/node/{node_id}", json=payload)
        return NodeResponse.model_validate(data)

    async def delete_node(self, node_id: int) -> str:
        """DELETE /api/node/{id} — удалить ноду."""
        data = await self._request("DELETE", f"/api/node/{node_id}")
        return str(data)

    async def list_nodes(self) -> List[NodeResponse]:
        """GET /api/nodes — список нод."""
        data = await self._request("GET", "/api/nodes")
        return [NodeResponse.model_validate(item) for item in data]

    async def nodes_usage(self) -> NodesUsageResponse:
        """GET /api/nodes/usages — статистика трафика по нодам."""
        data = await self._request("GET", "/api/nodes/usages")
        return NodesUsageResponse.model_validate(data)

    # ------------------------------------------------------------------
    # System API
    # ------------------------------------------------------------------

    async def system_stats(self) -> SystemStats:
        """
        GET /api/system — общая статистика панели и пользователей.

        Название маршрута может отличаться в зависимости от версии Marzban,
        но в Swagger 0.8.4 он маппится на модель SystemStats.
        """
        data = await self._request("GET", "/api/system")
        return SystemStats.model_validate(data)


__all__ = ["MarzbanAPIClient", "MarzbanAPIError"]