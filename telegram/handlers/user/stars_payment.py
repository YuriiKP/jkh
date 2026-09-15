import logging

from aiogram import F
from aiogram.types import Message
from loader import db_manage, dp, subscription_service
from locales import get_text as _
from tariffs import get_tariff
from utils.admin_notify import notify_admin_about_purchase
from utils.marzban_api import MarzbanAPIError
from utils.subscription import SubscriptionError

logger = logging.getLogger(__name__)


@dp.message(F.successful_payment)
async def stars_payment_handler(message: Message):
    """
    Обработчик успешной оплаты через Telegram Stars.

    Раньше оплата звёздами не обрабатывалась вовсе: инвойс отправлялся,
    деньги списывались, но подписка не выдавалась. Теперь после успешной
    оплаты мы выдаём/продлеваем доступ через единый SubscriptionService
    (пользователь гарантированно попадает в нужную группу Pasarguard).
    """
    payment = message.successful_payment
    if payment is None or message.from_user is None:
        return

    user_id = message.from_user.id
    tariff = get_tariff(payment.invoice_payload)
    logger.info(
        f"Stars payment {payment.telegram_payment_charge_id}: user {user_id}, tariff {tariff.key}"
    )

    # Выдаём/продлеваем подписку (гарантирует доступ и группу)
    try:
        await subscription_service.grant(
            user_id=user_id,
            days=tariff.days,
            tariff=tariff.key,
            note=f"{message.from_user.first_name} @{message.from_user.username}",
        )
    except (SubscriptionError, MarzbanAPIError) as e:
        logger.error(f"Stars payment: не удалось выдать подписку {user_id}: {e}")
        await message.answer(_("payment_error"))
        return

    # Отменяем неиспользованный пробный период, если он был
    user_tg = await db_manage.get_user_by_id(user_id)
    if user_tg and user_tg[7] == "true":  # trial field
        await db_manage.update_user(user_id, trial="false")

    # Фиксируем платёж в БД
    await db_manage.add_payment(
        user_id=user_id,
        amount=payment.total_amount,
        currency=payment.currency,
        payload=tariff.key,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
        provider_payment_charge_id=payment.provider_payment_charge_id,
    )

    await message.answer(_("payment_success_stars", days=tariff.days))

    # Уведомляем главного админа о покупке
    await notify_admin_about_purchase(
        user_id=user_id,
        product=f"«{tariff.title}»",
        first_name=message.from_user.first_name,
        username=message.from_user.username,
    )
