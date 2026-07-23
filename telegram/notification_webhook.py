from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiohttp import web
from keyboards import *
from locales import Locales, setup_context
from storage import DB_M

logger = logging.getLogger(__name__)


def _stable_event_id(payload: dict) -> str:
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
    notify_secret: Optional[str] = None,
) -> None:
    """
    Регистрирует маршрут для приема webhook-уведомлений от панели.
    """
    path = (notify_path or "").strip()
    if not path:
        return
    if not path.startswith("/"):
        path = f"/{path}"

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
            logger.info(f"Пришло уведомление от панели. Тип: {payload.get('action')}")
        except Exception:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

        action = payload.get("action")
        if action != "reached_days_left":
            return web.json_response(
                {"ok": True, "ignored": True, "reason": "unsupported_action"}
            )

        # Извлекаем данные напрямую из payload, без Pydantic-валидации
        try:
            username = str(payload.get("username", ""))
            days_left = int(payload.get("days_left", 0))
        except (ValueError, TypeError):
            return web.json_response(
                {"ok": False, "error": "invalid_payload"}, status=400
            )

        if not username:
            return web.json_response(
                {"ok": False, "error": "username_required"}, status=400
            )

        # В панели username = telegram user_id (см. create_user(username=str(user_id))).
        try:
            user_id = int(username)
        except ValueError:
            return web.json_response(
                {"ok": False, "error": "invalid_user_id"}, status=400
            )

        event_id = _stable_event_id(payload)

        is_new = await db_manage.register_pasarguard_notification_event(
            event_id=str(event_id),
            user_id=user_id,
            days_left=days_left,
        )
        if not is_new:
            return web.json_response({"ok": True, "duplicate": True})

        # Определяем язык пользователя и устанавливаем контекст локализации
        user_info = await db_manage.get_user_by_id(user_id)
        lang = str(user_info[6]) if user_info else "en"
        if lang not in ("ru", "en", "fa"):
            lang = "en"
        setup_context(locale, lang)

        try:
            await bot.send_message(
                chat_id=user_id, text=notification_days_left_text(days_left)
            )
            logger.info(
                f"Уведомление отправлено пользователю в Телеграм | user_id: {user_id}"
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            # Пользователь мог заблокировать бота/не начинал диалог — webhook считаем обработанным.
            logger.info(
                f"Ошибка при отправке уведомления в Телеграм | user_id: {user_id}"
            )
            return web.json_response(
                {"ok": True, "sent": False, "reason": "cannot_send"}
            )

        return web.json_response({"ok": True, "sent": True})

    app.router.add_post(path, pasarguard_notify_handler)
