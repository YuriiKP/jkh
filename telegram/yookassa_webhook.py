import asyncio
import ipaddress
import json
import logging
from typing import Optional

from aiogram import Bot
from aiohttp import web
from loader import db_manage, subscription_service, yookassa_client
from models.yookassa import YooKassaPayment, YooKassaWebhook
from pydantic import ValidationError
from tariffs import get_tariff
from utils.admin_notify import notify_admin_about_purchase
from utils.marzban_api import MarzbanAPIError
from utils.subscription import SubscriptionError

logger = logging.getLogger(__name__)

# Сериализует обработку успешных платежей: две копии одного и того же
# вебхука не должны выдавать подписку дважды.
_payment_processing_lock = asyncio.Lock()

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

# Те же адреса, разобранные в сети: сравнение строк вида "185.71.76.5"
# с "185.71.76.0/27" не работает, нужна проверка на вхождение в подсеть.
KNOWN_YOOKASSA_NETWORKS = tuple(
    ipaddress.ip_network(ip, strict=False) for ip in KNOWN_YOOKASSA_IPS
)


def _get_client_ip(request: web.Request) -> str | None:
    """
    Возвращает реальный IP клиента.

    Если бот работает за обратным прокси (в логах такие запросы приходят
    с адреса вида 172.18.0.3), настоящий адрес отправителя приходит
    в заголовке X-Forwarded-For — берём из него первый адрес.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first

    peer_name = (
        request.transport.get_extra_info("peername") if request.transport else None
    )
    if peer_name:
        return peer_name[0]

    return request.remote


def _is_known_yookassa_ip(ip: str) -> bool:
    """Проверяет, принадлежит ли адрес сетям ЮKassa (с поддержкой CIDR)."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False

    return any(address in network for network in KNOWN_YOOKASSA_NETWORKS)


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

    # Проверяем IP-адрес отправителя (с учётом обратного прокси)
    client_ip = _get_client_ip(request)

    if client_ip is None:
        logger.warning(
            "YooKassa webhook: не удалось определить IP отправителя. "
            "Proceeding anyway — payment will be verified via API."
        )
        return True

    if _is_known_yookassa_ip(client_ip):
        logger.debug(f"YooKassa webhook from known IP: {client_ip}")
        return True

    logger.warning(
        f"YooKassa webhook from unknown IP: {client_ip}. "
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


def _extract_user_id(payment: YooKassaPayment) -> int | None:
    """
    Извлекает user_id из metadata платежа.

    Возвращает None, если metadata отсутствует или user_id некорректен.
    """
    if not payment.metadata:
        logger.error(f"Missing metadata in payment: {payment.id}")
        return None

    metadata_dict = payment.metadata
    user_id_str = (
        metadata_dict.get("user_id")
        if isinstance(metadata_dict, dict)
        else getattr(metadata_dict, "user_id", None)
    )

    if not user_id_str:
        logger.error(f"Missing user_id in payment metadata: {payment.id}")
        return None

    try:
        return int(user_id_str)
    except (ValueError, TypeError):
        logger.error(f"Invalid user_id in metadata: {user_id_str}")
        return None


async def _payment_already_processed(user_id: int, payment_id: str) -> bool:
    """
    Проверяет, обрабатывался ли этот платёж ЮKassa ранее.

    Проверка идёт по таблице платежей (provider_payment_charge_id), поэтому
    не требует изменения схемы БД. Нужна, чтобы повторный вебхук с тем же
    payment.id не продлил подписку второй раз.
    """
    if not payment_id:
        return False

    try:
        payments = await db_manage.get_payments_by_user(user_id)
    except Exception as e:
        # Ошибка чтения БД не должна блокировать выдачу уже оплаченного доступа
        logger.error(
            f"Не удалось проверить дубли платежей для {user_id}: "
            f"{type(e).__name__}: {e}"
        )
        return False

    return any(
        payment.get("provider_payment_charge_id") == payment_id for payment in payments
    )


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
        user_id = _extract_user_id(payment)
        if user_id is None:
            return False

        metadata_dict = payment.metadata

        # Идемпотентность: один и тот же платёж может прийти повторно
        # (ЮKassa ретраит вебхук, если не получила 200). Подписку второй раз
        # не выдаём, иначе пользователь получит двойной срок.
        if await _payment_already_processed(user_id, payment.id):
            logger.info(f"Payment {payment.id} already processed — skipping")
            return True

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

        # Конвертируем amount в число (просто логируем, не проверяем строго)
        try:
            amount_value = float(amount)
            logger.info(f"Payment amount: {amount_value} {currency}")
        except (ValueError, TypeError):
            logger.error(f"Invalid amount value: {amount}")
            return False

        # Определяем тариф из метаданных (неизвестный тариф -> тариф по умолчанию)
        tariff_key = (
            metadata_dict.get("tariff") if isinstance(metadata_dict, dict) else None
        )
        tariff = get_tariff(tariff_key)
        days = tariff.days
        logger.info(f"Tariff: {tariff.key}, days: {days}")

        # Если есть не активированный пробный период, отменяем его
        user_tg = await db_manage.get_user_by_id(user_id)
        if user_tg and user_tg[7] == "true":  # trial field
            await db_manage.update_user(user_id, trial="false")

        # Выдаём или продлеваем доступ. Сервис гарантирует, что пользователь
        # окажется в нужной группе Pasarguard (по умолчанию "main") и получит
        # активную подписку, иначе у оплатившего не будет доступа к сервису.
        try:
            await subscription_service.grant(
                user_id=user_id,
                days=days,
                tariff=tariff.key,
                note=f"User {user_id}",
            )
        except SubscriptionError as e:
            logger.error(f"Не удалось выдать подписку пользователю {user_id}: {e}")
            return False
        except MarzbanAPIError as e:
            logger.error(f"Marzban API error: {e.message}")
            return False

        # Сохраняем информацию о платеже в базе данных
        amount_in_kopecks = int(amount_value * 100)

        await db_manage.add_payment(
            user_id=user_id,
            amount=amount_in_kopecks,
            currency=currency,
            payload=tariff_key,
            telegram_payment_charge_id="",
            provider_payment_charge_id=payment.id,
            status="completed",
        )

        # Отправляем уведомление пользователю
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"✅ Оплата прошла успешно! Ваша подписка обновлена на {days} дней. 🚀",
            )
            logger.info(f"Success notification sent to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send notification to user {user_id}: {e}")

        # Уведомляем главного админа о покупке
        await notify_admin_about_purchase(
            user_id=user_id,
            product=f"«{tariff.title}»",
            first_name=user_tg[2] if user_tg else None,
            username=user_tg[1] if user_tg else None,
        )

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

            # Отмена платежа: просто подтверждаем получение (200), чтобы ЮKassa
            # не ретраила вебхук. Пользователя не уведомляем.
            if webhook_data.event == "payment.canceled":
                logger.info(f"Payment {webhook_data.object.id} canceled")
                return web.json_response({"ok": True, "canceled": True})

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

            # Обрабатываем платеж под локом: две копии одного вебхука
            # не должны выдать подписку дважды
            async with _payment_processing_lock:
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
