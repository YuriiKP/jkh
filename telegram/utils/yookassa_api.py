import asyncio
import logging
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from yookassa import Configuration, Payment
from yookassa.domain.common.confirmation_type import ConfirmationType
from yookassa.domain.response.payment_response import PaymentResponse

logger = logging.getLogger(__name__)

# Таймаут одного HTTP-запроса к API ЮKassa, секунды.
# По умолчанию SDK ждёт 1800 с на попытку и делает до 3 попыток — такие
# значения недопустимы внутри обработчика Telegram-апдейта.
DEFAULT_REQUEST_TIMEOUT = 10
DEFAULT_MAX_ATTEMPTS = 2


class YooKassaAPIClient:
    """Клиент для работы с API ЮKassa.

    SDK `yookassa` полностью синхронный (построен на `requests`), поэтому
    все обращения к API выполняются в отдельном потоке через
    `asyncio.to_thread` — иначе блокируется event loop всего бота и
    перестают обрабатываться Telegram-апдейты и вебхуки.
    """

    def __init__(
        self,
        shop_id: str,
        secret_key: str,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ):
        """
        Инициализация клиента ЮKassa.

        Args:
            shop_id: ID магазина в ЮKassa
            secret_key: Секретный ключ магазина
            request_timeout: Таймаут одного запроса к API, секунды
            max_attempts: Количество попыток запроса внутри SDK
        """
        self.shop_id = shop_id
        self.secret_key = secret_key
        self.request_timeout = request_timeout
        self.max_attempts = max_attempts
        # Запас поверх внутренних таймаутов SDK: гарантирует, что ожидание
        # в обработчике конечно, даже если SDK поведёт себя неожиданно.
        self.task_timeout = request_timeout * max_attempts + 5

        # Настройка конфигурации ЮKassa
        Configuration.configure(
            shop_id,
            secret_key,
            timeout=request_timeout,
            max_attempts=max_attempts,
        )
        logger.info(
            f"YooKassa client initialized with shop_id: {shop_id[:8]}..., "
            f"timeout={request_timeout}s, max_attempts={max_attempts}"
        )

    async def _run_sync(self, func: Callable[..., Any], *args: Any) -> Any:
        """
        Выполняет синхронный вызов SDK ЮKassa в отдельном потоке.

        `asyncio.wait_for` не убивает поток, но позволяет обработчику
        не зависнуть, если API ЮKassa не отвечает.
        """
        return await asyncio.wait_for(
            asyncio.to_thread(func, *args),
            timeout=self.task_timeout,
        )

    async def create_payment(
        self,
        amount: float,
        currency: str,
        description: str,
        user_id: int,
        return_url: str,
        metadata: Optional[Dict[str, Any]] = None,
        idempotence_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Создает платеж в ЮKassa.

        Args:
            amount: Сумма платежа
            currency: Валюта (например, "RUB")
            description: Описание платежа
            user_id: ID пользователя в Telegram
            return_url: URL для возврата после оплаты
            metadata: Дополнительные метаданные
            idempotence_key: Ключ идемпотентности. Если не задан — генерируется
                автоматически (каждый вызов создаёт новый платёж). Чтобы
                повторная обработка одного и того же апдейта не создавала
                дубль платежа, ключ нужно генерировать на уровне вызывающего кода.

        Returns:
            Словарь с данными платежа или None в случае ошибки
        """
        try:
            # Подготавливаем метаданные
            payment_metadata = {"user_id": str(user_id)}

            if metadata:
                payment_metadata.update(metadata)

            # Создаем запрос на создание платежа
            payment_request = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": currency,
                },
                "confirmation": {
                    "type": ConfirmationType.REDIRECT,
                    "return_url": return_url,
                },
                "capture": True,  # Автоматическое списание средств
                "description": description,
                "metadata": payment_metadata,
            }

            # Ключ идемпотентности: повторный запрос с тем же ключом вернёт
            # уже созданный платёж, а не создаст второй.
            key = idempotence_key or str(uuid4())

            # Создаем платеж (синхронный SDK — только в отдельном потоке)
            payment_response: PaymentResponse = await self._run_sync(
                Payment.create, payment_request, key
            )

            logger.info(
                f"Payment created: {payment_response.id} for user {user_id} "
                f"(idempotence_key={key})"
            )

            # Возвращаем данные платежа
            result = {
                "id": payment_response.id,
                "status": payment_response.status,
                "amount": {
                    "value": float(payment_response.amount.value),
                    "currency": payment_response.amount.currency,
                },
                "created_at": payment_response.created_at,
                "description": payment_response.description,
            }

            # Добавляем URL подтверждения если есть
            if (
                hasattr(payment_response, "confirmation")
                and payment_response.confirmation
            ):
                result["confirmation_url"] = (
                    payment_response.confirmation.confirmation_url
                )

            # Добавляем метаданные если есть
            if hasattr(payment_response, "metadata") and payment_response.metadata:
                result["metadata"] = payment_response.metadata

            return result

        except Exception as e:
            logger.error(
                f"Error creating YooKassa payment for user {user_id}: "
                f"{type(e).__name__}: {e}"
            )
            return None

    async def get_payment_status(self, payment_id: str) -> Optional[str]:
        """
        Получает статус платежа.

        Args:
            payment_id: ID платежа в ЮKassa

        Returns:
            Статус платежа или None в случае ошибки
        """
        try:
            payment_response = await self._run_sync(Payment.find_one, payment_id)
            return payment_response.status
        except Exception as e:
            logger.error(
                f"Error getting payment status for {payment_id}: "
                f"{type(e).__name__}: {e}"
            )
            return None

    async def cancel_payment(
        self, payment_id: str, idempotence_key: Optional[str] = None
    ) -> bool:
        """
        Отменяет платеж.

        Args:
            payment_id: ID платежа в ЮKassa
            idempotence_key: Ключ идемпотентности (по умолчанию генерируется)

        Returns:
            True если отмена успешна, False в противном случае
        """
        try:
            payment_response = await self._run_sync(
                Payment.cancel, payment_id, idempotence_key or str(uuid4())
            )
            return payment_response.status == "canceled"
        except Exception as e:
            logger.error(
                f"Error canceling payment {payment_id}: {type(e).__name__}: {e}"
            )
            return False

    async def create_payment_link(
        self,
        amount: float,
        currency: str,
        description: str,
        user_id: int,
        return_url: str,
        metadata: Optional[Dict[str, Any]] = None,
        idempotence_key: Optional[str] = None,
    ) -> Optional[str]:
        """
        Создает ссылку на оплату.

        Args:
            amount: Сумма платежа
            currency: Валюта (например, "RUB")
            description: Описание платежа
            user_id: ID пользователя в Telegram
            return_url: URL для возврата после оплаты
            metadata: Дополнительные метаданные (будет передано в create_payment)
            idempotence_key: Ключ идемпотентности (см. create_payment)

        Returns:
            Ссылка на оплату или None в случае ошибки
        """
        payment_data = await self.create_payment(
            amount=amount,
            currency=currency,
            description=description,
            user_id=user_id,
            return_url=return_url,
            metadata=metadata,
            idempotence_key=idempotence_key,
        )

        if payment_data and "confirmation_url" in payment_data:
            return payment_data["confirmation_url"]

        return None
