from __future__ import annotations

import hashlib
import json
from typing import Optional

from aiohttp import web
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from pydantic import ValidationError

from models.notification import ReachedDaysLeft, Notification
from storage import DB_M
from keyboards import *


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
        except Exception:
            return web.json_response(
                {"ok": False, "error": "invalid_json"}, status=400
            )

        # Все уведомления приходят в общей схеме Notification.*.
        # Нас интересует только reached_days_left, остальные игнорируем.
        action = payload.get("action")
        if action != Notification.Type.reached_days_left:
            return web.json_response(
                {"ok": True, "ignored": True, "reason": "unsupported_action"}
            )

        try:
            notification = ReachedDaysLeft.model_validate(payload)
        except ValidationError as e:
            return web.json_response(
                {"ok": False, "error": "invalid_payload", "details": e.errors()},
                status=400,
            )

        days_left = int(notification.days_left)

        # В панели username = telegram user_id (см. create_user(username=str(user_id))).
        try:
            user_id = int(notification.username)
        except Exception:
            return web.json_response(
                {"ok": False, "error": "user_id_required"}, status=400
            )

        event_id = _stable_event_id(payload)

        is_new = await db_manage.register_pasarguard_notification_event(
            event_id=str(event_id),
            user_id=user_id,
            days_left=days_left,
        )
        if not is_new:
            return web.json_response({"ok": True, "duplicate": True})

        try:
            await bot.send_message(chat_id=user_id, text=notification_days_left_text(days_left))
        except (TelegramForbiddenError, TelegramBadRequest):
            # Пользователь мог заблокировать бота/не начинал диалог — webhook считаем обработанным.
            return web.json_response(
                {"ok": True, "sent": False, "reason": "cannot_send"}
            )

        return web.json_response({"ok": True, "sent": True})


    app.router.add_post(path, pasarguard_notify_handler)

