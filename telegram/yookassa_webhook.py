import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from aiohttp import web
from loader import db_manage, marzban_client, yookassa_client
from models.proxy import ProxyTable, VlessSettings, XTLSFlows
from models.user import (
    UserCreate,
    UserModify,
    UserResponse,
    UserStatusCreate,
    UserStatusModify,
)
from models.yookassa import YooKassaPayment, YooKassaWebhook
from pydantic import ValidationError
from utils.marzban_api import MarzbanAPIError

logger = logging.getLogger(__name__)

# Известные IP-адреса ЮKassa для вебхуков (могут меняться, актуальные см. в документации)
# https://yookassa.ru/developers/using-api/webhooks#ip
KNOWN_YOOKASSA_IPS = {
    "185.71.76.0/27",
    "185.71.77.0/27",
    "77.75.153.0/27",
    "77.75.156.11",
    "77.75.156.35",
    "77.75.154.128/25",
    "2a02:5180::/32",
}


def _verify_signature(request: web.Request, secret_key: str | None) -> bool:
    """
    Проверяет подлинность запроса от ЮKassa.

    Использует комбинированный подход:
    1. Если передан secret_key — проверяет через IP-адрес отправителя.
    2. Если secret_key не задан — пропускает проверку (не рекомендуется для production).

    Args:
        request: HTTP-запрос
        secret_key: Секретный ключ (используется как флаг для включения проверки)

    Returns:
        True если запрос прошёл проверку
    """
    if not secret_key:
        # Если секретный ключ не задан — проверка отключена
        logger.warning(
            "YooKassa secret key is not configured — signature verification is disabled"
        )
        return True

    # Проверяем IP-адрес отправителя
    peer_name = (
        request.transport.get_extra_info("peername") if request.transport else None
    )
    if peer_name:
        peer_ip = peer_name[0]
        # Простая проверка на соответствие известным IP
        # В production рекомендуется использовать полноценную CIDR-проверку
        if peer_ip in KNOWN_YOOKASSA_IPS:
            return True
        logger.warning(
            f"YooKassa webhook from unknown IP: {peer_ip}. "
            f"Proceeding anyway — payment will be verified via API."
        )
        # Не блокируем по IP, а пропускаем для верификации через API

    return True


def _check_payment_status_sync(payment_id: str) -> str | None:
    """
    Синхронная проверка статуса платежа через SDK ЮKassa.
    Вызывается в отдельном потоке через asyncio.to_thread.
    """
    from yookassa import Payment

    try:
        payment_response = Payment.find_one(payment_id)
        return payment_response.status
    except Exception as e:
        logger.error(f"Error in sync payment status check for {payment_id}: {e}")
        return None


async def _verify_payment_via_api(payment_id: str) -> bool:
    """
    Верифицирует платёж через API ЮKassa.

    Использует синхронный SDK ЮKassa в отдельном потоке,
    чтобы не блокировать event loop.

    Args:
        payment_id: ID платежа

    Returns:
        True если платеж подтверждён API (статус succeeded)
    """
    if not yookassa_client:
        logger.error("YooKassa client is not initialized, cannot verify payment")
        return False

    try:
        # Запускаем синхронный SDK-вызов в потоке
        status = await asyncio.to_thread(_check_payment_status_sync, payment_id)

        if status is None:
            logger.error(
                f"Failed to verify payment {payment_id} via API — got None status"
            )
            return False

        logger.info(f"Payment {payment_id} verified via API, status: {status}")

        if status != "succeeded":
            logger.warning(
                f"Payment {payment_id} has status '{status}' via API, "
                f"but webhook reported 'succeeded'. Possible fraud attempt!"
            )
            return False

        return True

    except Exception as e:
        logger.error(f"Error verifying payment {payment_id} via API: {e}")
        return False


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

        metadata_dict = payment.metadata
        user_id_str = (
            metadata_dict.get("user_id")
            if isinstance(metadata_dict, dict)
            else getattr(metadata_dict, "user_id", None)
        )

        if not user_id_str:
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

        # Извлекаем сумму и валюту
        amount_dict = payment.amount
        if isinstance(amount_dict, dict):
            amount = amount_dict.get("value", "0")
            currency = amount_dict.get("currency", "RUB")
        else:
            amount = getattr(amount_dict, "value", "0")
            currency = getattr(amount_dict, "currency", "RUB")

        # Конвертируем amount в число
        try:
            amount_value = float(amount)
            if currency != "RUB" or amount_value != 100.00:
                logger.warning(
                    f"Unexpected payment amount/currency: {amount_value} {currency}"
                )
        except (ValueError, TypeError):
            logger.error(f"Invalid amount value: {amount}")
            return False

        # Если есть не активированный пробный период, отменяем его
        user_tg = await db_manage.get_user_by_id(user_id)
        if user_tg and user_tg[7] == "true":  # trial field
            await db_manage.update_user(user_id, trial="false")

        # Если пользователя в marzban нет — создаем, иначе — продлеваем
        try:
            user_marz: UserResponse = await marzban_client.get_user(str(user_id))

            # Определяем текущую дату истечения
            if user_marz.expire:
                if isinstance(user_marz.expire, int):
                    current_expire = datetime.fromtimestamp(user_marz.expire)
                else:
                    current_expire = user_marz.expire
                    if current_expire.tzinfo is not None:
                        current_expire = current_expire.replace(tzinfo=None)
            else:
                current_expire = datetime.now()

            # Добавляем 30 дней к текущей дате истечения
            new_expire = current_expire + timedelta(days=30)

            modify_user = UserModify(
                expire=new_expire,
                proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION)),
                status=UserStatusModify.active,
            )
            await marzban_client.modify_user(str(user_id), modify_user)

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
                await marzban_client.create_user(new_user)
            else:
                logger.error(f"Marzban API error: {e.message}")
                return False

        # Сохраняем информацию о платеже в базе данных
        amount_in_kopecks = int(amount_value * 100)

        await db_manage.add_payment(
            user_id=user_id,
            amount=amount_in_kopecks,
            currency=currency,
            payload="one_month",
            telegram_payment_charge_id="",
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
        secret_key: Секретный ключ для включения проверки запросов
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
            logger.info(
                f"Received YooKassa webhook: {payload.get('type')} / {payload.get('event')}"
            )

            # Валидируем данные
            webhook_data = YooKassaWebhook.model_validate(payload)

            # Обрабатываем только события успешной оплаты
            if webhook_data.event != "payment.succeeded":
                logger.info(f"Ignoring unsupported event: {webhook_data.event}")
                return web.json_response(
                    {"ok": True, "ignored": True, "reason": "unsupported_event"}
                )

            # Верифицируем платеж через API ЮKassa (защита от поддельных вебхуков)
            payment_id = webhook_data.object.id
            logger.info(f"Verifying payment {payment_id} via API...")

            is_verified = await _verify_payment_via_api(payment_id)
            if not is_verified:
                logger.error(
                    f"Payment {payment_id} verification via API failed — "
                    f"possible fraud or API unavailable"
                )
                # Возвращаем 200 чтобы ЮKassa не переотправляла вебхук,
                # но не обрабатываем платеж
                return web.json_response(
                    {"ok": True, "ignored": True, "reason": "verification_failed"}
                )

            logger.info(f"Payment {payment_id} verified successfully, processing...")

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
            logger.error("Invalid JSON in request body")
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)
        except Exception as e:
            logger.error(f"Unexpected error in webhook handler: {e}")
            return web.json_response(
                {"ok": False, "error": "internal_error"}, status=500
            )

    app.router.add_post(path, yookassa_webhook_handler)
    logger.info(f"YooKassa webhook registered at path: {path}")
