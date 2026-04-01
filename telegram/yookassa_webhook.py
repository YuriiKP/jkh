import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from aiohttp import web
from loader import db_manage, marzban_client
from models.proxy import ProxyTable, VlessSettings, XTLSFlows
from models.user import (
    UserCreate,
    UserModify,
    UserResponse,
    UserStatusCreate,
    UserStatusModify,
)
from pydantic import BaseModel, Field, ValidationError
from utils.marzban_api import MarzbanAPIError

logger = logging.getLogger(__name__)


class YooKassaPayment(BaseModel):
    """Модель платежа от ЮKassa"""

    id: str = Field(..., alias="id")
    status: str = Field(..., alias="status")
    amount: dict = Field(..., alias="amount")
    description: Optional[str] = Field(None, alias="description")
    metadata: Optional[dict] = Field(None, alias="metadata")
    recipient: Optional[dict] = Field(None, alias="recipient")
    created_at: str = Field(..., alias="created_at")
    captured_at: Optional[str] = Field(None, alias="captured_at")
    payment_method: Optional[dict] = Field(None, alias="payment_method")
    test: bool = Field(False, alias="test")


class YooKassaWebhook(BaseModel):
    """Модель вебхука от ЮKassa"""

    type: str = Field(..., alias="type")
    event: str = Field(..., alias="event")
    object: YooKassaPayment = Field(..., alias="object")


def _verify_signature(request: web.Request, secret_key: str | None) -> bool:
    """
    Проверяет подпись запроса от ЮKassa.

    ЮKassa отправляет подпись в заголовке 'Content-SHA256'.
    Подпись вычисляется как SHA256 от тела запроса в кодировке base64.
    """
    if not secret_key:
        return True  # Если секретный ключ не задан, пропускаем проверку

    signature = request.headers.get("Content-SHA256")
    if not signature:
        logger.warning("Missing Content-SHA256 header")
        return False

    # Получаем тело запроса
    body = request._body if hasattr(request, "_body") else None
    if not body:
        # Если тело еще не прочитано, читаем его
        body = request.content.read()
        request._body = body  # Кэшируем для повторного использования

    # Вычисляем SHA256 от тела
    body_hash = hashlib.sha256(body).digest()
    import base64

    expected_signature = base64.b64encode(body_hash).decode("utf-8")

    # Сравниваем подписи
    return signature == expected_signature


async def _process_successful_payment(payment: YooKassaPayment, bot: Bot) -> bool:
    """
    Обрабатывает успешный платеж.

    Args:
        payment: Данные платежа от ЮKassa
        bot: Экземпляр бота для отправки уведомлений

    Returns:
        True если обработка прошла успешно, False в противном случае
    """
    try:
        # Извлекаем user_id из metadata
        if not payment.metadata:
            logger.error(f"Missing metadata in payment: {payment.id}")
            return False

        # Метаданные могут быть в разных форматах (dict или объект)
        metadata_dict = payment.metadata
        if hasattr(metadata_dict, "user_id"):
            # Если это объект с атрибутами
            user_id_str = metadata_dict.user_id
        elif isinstance(metadata_dict, dict) and "user_id" in metadata_dict:
            # Если это словарь
            user_id_str = metadata_dict["user_id"]
        else:
            logger.error(f"Missing user_id in payment metadata: {payment.id}")
            return False

        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            logger.error(f"Invalid user_id in metadata: {user_id_str}")
            return False

        # Проверяем, что платеж действительно успешный и оплачен
        if payment.status != "succeeded":
            logger.warning(
                f"Payment {payment.id} is not succeeded, status: {payment.status}"
            )
            return False

        # Проверяем сумму платежа (ожидаем 100 рублей = 10000 копеек)
        amount_dict = payment.amount
        if hasattr(amount_dict, "value"):
            amount = amount_dict.value
        elif isinstance(amount_dict, dict) and "value" in amount_dict:
            amount = amount_dict["value"]
        else:
            logger.error(f"Invalid amount format in payment: {payment.id}")
            return False

        if hasattr(amount_dict, "currency"):
            currency = amount_dict.currency
        elif isinstance(amount_dict, dict) and "currency" in amount_dict:
            currency = amount_dict["currency"]
        else:
            currency = "RUB"

        # Конвертируем amount в число если нужно
        try:
            amount_value = float(amount)
            # Проверяем сумму (100 рублей = 100.00)
            if currency != "RUB" or amount_value != 100.00:
                logger.warning(
                    f"Unexpected payment amount/currency: {amount_value} {currency}"
                )
                # Все равно обрабатываем, но логируем предупреждение
        except (ValueError, TypeError):
            logger.error(f"Invalid amount value: {amount}")
            return False

        # Если есть не активированный пробный период, отменяем его
        user_tg = await db_manage.get_user_by_id(user_id)
        if user_tg and user_tg[7] == "true":  # trial field
            await db_manage.update_user(user_id, trial="false")

        # Если пользователя в marzban нет создаем его
        try:
            user_marz: UserResponse = await marzban_client.get_user(str(user_id))

            # Определяем текущую дату истечения
            if user_marz.expire:
                # Если expire это timestamp (int), конвертируем в datetime
                if isinstance(user_marz.expire, int):
                    current_expire = datetime.fromtimestamp(user_marz.expire)
                else:
                    current_expire = user_marz.expire
                    # Если datetime имеет timezone, конвертируем в naive datetime
                    if current_expire.tzinfo is not None:
                        current_expire = current_expire.replace(tzinfo=None)
            else:
                # Если подписки нет, начинаем с текущей даты
                current_expire = datetime.now()

            # Добавляем 30 дней к текущей дате истечения
            new_expire = current_expire + timedelta(days=30)

            modify_user = UserModify(
                expire=new_expire,
                proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION)),
                status=UserStatusModify.active,
            )
            modified_user: UserResponse = await marzban_client.modify_user(
                str(user_id), modify_user
            )
        except MarzbanAPIError as e:
            if e.status == 404:
                new_user = UserCreate(
                    username=str(user_id),
                    note=f"User {user_id}",
                    status=UserStatusCreate.active,
                    expire=datetime.now() + timedelta(days=30),
                    group_ids=[1],
                    proxy_settings=ProxyTable(
                        vless=VlessSettings(flow=XTLSFlows.VISION)
                    ),
                )
                created_user: UserResponse = await marzban_client.create_user(new_user)
            else:
                logger.error(f"Marzban API error: {e.message}")
                return False

        # Сохраняем информацию о платеже в базе данных
        # Конвертируем сумму в копейки для хранения
        amount_in_kopecks = int(float(amount) * 100)

        await db_manage.add_payment(
            user_id=user_id,
            amount=amount_in_kopecks,
            currency=currency,
            payload="one_month",
            telegram_payment_charge_id="",  # Не используется для прямых платежей
            provider_payment_charge_id=payment.id,
            status="completed",
        )

        # Отправляем уведомление пользователю
        try:
            await bot.send_message(
                chat_id=user_id,
                text="✅ Оплата прошла успешно! Ваша подписка обновлена на 30 дней. 🚀",
            )
            logger.info(f"Success notification sent to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send notification to user {user_id}: {e}")
            # Продолжаем обработку, даже если не удалось отправить уведомление

        return True

    except Exception as e:
        logger.error(f"Error processing payment {payment.id}: {e}")
        return False


def register_yookassa_webhook_route(
    app: web.Application,
    *,
    bot: Bot,
    webhook_path: str,
    secret_key: Optional[str] = None,
) -> None:
    """
    Регистрирует маршрут для приема webhook-уведомлений от ЮKassa.

    Args:
        app: Приложение aiohttp
        bot: Экземпляр бота для отправки уведомлений
        webhook_path: Путь для вебхука
        secret_key: Секретный ключ для проверки подписи
    """
    path = (webhook_path or "").strip()
    if not path:
        logger.warning("YooKassa webhook path is empty, skipping registration")
        return
    if not path.startswith("/"):
        path = f"/{path}"

    async def yookassa_webhook_handler(request: web.Request) -> web.Response:
        # Проверяем подпись запроса
        if not _verify_signature(request, secret_key):
            return web.json_response(
                {"ok": False, "error": "invalid_signature"}, status=401
            )

        try:
            # Парсим JSON запрос
            payload = await request.json()
            logger.info(f"Received YooKassa webhook: {payload.get('type')}")

            # Валидируем данные
            webhook_data = YooKassaWebhook.model_validate(payload)

            # Обрабатываем только события успешной оплаты
            if webhook_data.event != "payment.succeeded":
                return web.json_response(
                    {"ok": True, "ignored": True, "reason": "unsupported_event"}
                )

            # Обрабатываем платеж
            success = await _process_successful_payment(webhook_data.object, bot)

            if success:
                return web.json_response({"ok": True, "processed": True})
            else:
                return web.json_response(
                    {"ok": False, "error": "payment_processing_failed"}, status=500
                )

        except ValidationError as e:
            logger.error(f"Validation error: {e.errors()}")
            return web.json_response(
                {"ok": False, "error": "invalid_payload", "details": str(e.errors())},
                status=400,
            )
        except json.JSONDecodeError:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return web.json_response(
                {"ok": False, "error": "internal_error"}, status=500
            )

    app.router.add_post(path, yookassa_webhook_handler)
    logger.info(f"YooKassa webhook registered at path: {path}")
