import logging
from typing import Any, Dict, Optional

from yookassa import Configuration, Payment
from yookassa.domain.common.confirmation_type import ConfirmationType
from yookassa.domain.response.payment_response import PaymentResponse

logger = logging.getLogger(__name__)


class YooKassaAPIClient:
    """Клиент для работы с API ЮKassa"""

    def __init__(self, shop_id: str, secret_key: str):
        """
        Инициализация клиента ЮKassa.

        Args:
            shop_id: ID магазина в ЮKassa
            secret_key: Секретный ключ магазина
        """
        self.shop_id = shop_id
        self.secret_key = secret_key

        # Настройка конфигурации ЮKassa
        Configuration.configure(shop_id, secret_key)
        logger.info(f"YooKassa client initialized with shop_id: {shop_id[:8]}...")

    async def create_payment(
        self,
        amount: float,
        currency: str,
        description: str,
        user_id: int,
        return_url: str,
        metadata: Optional[Dict[str, Any]] = None,
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

            # Создаем платеж
            payment_response: PaymentResponse = Payment.create(payment_request)

            logger.info(f"Payment created: {payment_response.id} for user {user_id}")

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
            logger.error(f"Error creating YooKassa payment for user {user_id}: {e}")
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
            payment_response = Payment.find_one(payment_id)
            return payment_response.status
        except Exception as e:
            logger.error(f"Error getting payment status for {payment_id}: {e}")
            return None

    async def cancel_payment(self, payment_id: str) -> bool:
        """
        Отменяет платеж.

        Args:
            payment_id: ID платежа в ЮKassa

        Returns:
            True если отмена успешна, False в противном случае
        """
        try:
            payment_response = Payment.cancel(payment_id)
            return payment_response.status == "canceled"
        except Exception as e:
            logger.error(f"Error canceling payment {payment_id}: {e}")
            return False

    async def create_payment_link(
        self,
        amount: float,
        currency: str,
        description: str,
        user_id: int,
        return_url: str,
    ) -> Optional[str]:
        """
        Создает ссылку на оплату.

        Args:
            amount: Сумма платежа
            currency: Валюта (например, "RUB")
            description: Описание платежа
            user_id: ID пользователя в Telegram
            return_url: URL для возврата после оплаты

        Returns:
            Ссылка на оплату или None в случае ошибки
        """
        payment_data = await self.create_payment(
            amount=amount,
            currency=currency,
            description=description,
            user_id=user_id,
            return_url=return_url,
        )

        if payment_data and "confirmation_url" in payment_data:
            return payment_data["confirmation_url"]

        return None
