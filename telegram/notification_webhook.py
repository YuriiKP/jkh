from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiohttp import web
from locales import Locales, setup_context
from locales import get_text as _
from storage import DB_M
from utils.marzban_api import MarzbanAPIError
from utils.user_template import UserTemplateError, UserTemplateService

logger = logging.getLogger(__name__)


def _stable_event_id(payload: dict[str, Any]) -> str:
    """
    Детерминированный id события, если отдельный идентификатор
    не передан панелью.
    """
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def register_pasarguard_notification_route(
    app: web.Application,
    *,
    db_manage: DB_M,
    bot: Bot,
    locale: Locales,
    notify_path: str,
    notify_secret: str | None = None,
    user_template_service: UserTemplateService | None = None,
) -> None:
    """
    Регистрирует маршрут для приема webhook-уведомлений от панели.

    Поддерживаемые действия панели:
    - reached_days_left — напоминание о скором окончании подписки;
    - user_expired — подписка закончилась: применяем к пользователю шаблон
      (UserTemplateService) и уведомляем его.
    """
    path = (notify_path or "").strip()
    if not path:
        return
    if not path.startswith("/"):
        path = f"/{path}"

    async def _setup_user_lang(user_id: int) -> None:
        """Определяет язык пользователя и устанавливает контекст локализации."""
        user_info = await db_manage.get_user_by_id(user_id)
        lang = str(user_info[6]) if user_info else "en"
        if lang not in ("ru", "en", "fa"):
            lang = "en"
        setup_context(locale, lang)

    async def _send_user_message(user_id: int, text: str) -> bool:
        """Отправляет сообщение пользователю, не падая при блокировке бота."""
        try:
            await bot.send_message(chat_id=user_id, text=text)
            logger.info(
                "Уведомление отправлено пользователю в Телеграм | user_id: %s", user_id
            )
            return True
        except (TelegramForbiddenError, TelegramBadRequest):
            logger.info(
                "Ошибка при отправке уведомления в Телеграм | user_id: %s", user_id
            )
            return False

    async def _handle_days_left(payload: dict[str, Any], user_id: int) -> web.Response:
        """Напоминание о скором окончании подписки (поведение не менялось)."""
        try:
            days_left = int(payload.get("days_left", 0))
        except (ValueError, TypeError):
            return web.json_response(
                {"ok": False, "error": "invalid_payload"}, status=400
            )

        event_id = _stable_event_id(payload)

        is_new = await db_manage.register_pasarguard_notification_event(
            event_id=str(event_id),
            user_id=user_id,
            days_left=days_left,
        )
        if not is_new:
            return web.json_response({"ok": True, "duplicate": True})

        await _setup_user_lang(user_id)
        sent = await _send_user_message(
            user_id, _("notification_days_left_text", days_left=days_left)
        )
        return web.json_response({"ok": True, "sent": sent})

    async def _handle_user_expired(
        payload: dict[str, Any], user_id: int, username: str
    ) -> web.Response:
        """Подписка закончилась: применяем шаблон и уведомляем пользователя."""
        if user_template_service is None or not user_template_service.enabled:
            logger.warning(
                "Получено событие user_expired, но шаблон не настроен (EXPIRED_TEMPLATE_NAME) — пропускаем"
            )
            return web.json_response(
                {"ok": True, "ignored": True, "reason": "template_not_configured"}
            )

        # Для дедупликации берём только стабильные поля: повторная доставка
        # того же события даст тот же id, а новое истечение (после продления) — новый.
        user_payload = payload.get("user") or {}
        event_id = _stable_event_id(
            {
                "action": "user_expired",
                "username": username,
                "expire": user_payload.get("expire"),
                "edit_at": user_payload.get("edit_at"),
            }
        )

        is_new = await db_manage.register_pasarguard_notification_event(
            event_id=str(event_id),
            user_id=user_id,
            days_left=0,
        )
        if not is_new:
            return web.json_response({"ok": True, "duplicate": True})

        applied = True
        try:
            user = await user_template_service.apply(username)
            logger.info(
                "Пользователю %s применён шаблон после окончания подписки",
                user.username,
            )
        except (UserTemplateError, MarzbanAPIError) as e:
            applied = False
            logger.error("Не удалось применить шаблон пользователю %s: %s", username, e)

        await _setup_user_lang(user_id)
        sent = await _send_user_message(user_id, _("notification_user_expired_text"))

        return web.json_response({"ok": True, "applied": applied, "sent": sent})

    async def pasarguard_notify_handler(request: web.Request) -> web.Response:
        # Простая shared-secret аутентификация по заголовку.
        if notify_secret:
            got = request.headers.get("X-Pasarguard-Secret") or request.headers.get(
                "X-Webhook-Secret"
            )
            if got != notify_secret:
                return web.json_response(
                    {"ok": False, "error": "unauthorized"}, status=401
                )

        try:
            payload_list = await request.json()
            payload = payload_list[0]
            logger.info("Пришло уведомление от панели. Тип: %s", payload.get("action"))
        except Exception:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

        action = payload.get("action")

        # В панели username = telegram user_id (см. create_user(username=str(user_id))).
        username = str(
            payload.get("username") or (payload.get("user") or {}).get("username") or ""
        )
        if not username:
            return web.json_response(
                {"ok": False, "error": "username_required"}, status=400
            )
        try:
            user_id = int(username)
        except ValueError:
            return web.json_response(
                {"ok": False, "error": "invalid_user_id"}, status=400
            )

        if action == "reached_days_left":
            return await _handle_days_left(payload, user_id)

        if action == "user_expired":
            return await _handle_user_expired(payload, user_id, username)

        return web.json_response(
            {"ok": True, "ignored": True, "reason": "unsupported_action"}
        )

    app.router.add_post(path, pasarguard_notify_handler)
