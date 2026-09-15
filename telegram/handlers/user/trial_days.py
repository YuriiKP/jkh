import logging

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from keyboards import user_menu
from loader import (
    db_manage,
    dp,
    get_full_subscription_url,
    subscription_service,
)
from locales import get_text as _
from utils.marzban_api import MarzbanAPIError
from utils.subscription import SubscriptionError

from ..common import edit_menu_with_image

logger = logging.getLogger(__name__)


# Обработчик кнопки "Пробный период"
@dp.callback_query(F.data == "trial_bay")
async def trial_buy_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    user_id = query.from_user.id
    user_tg = await db_manage.get_user_by_id(user_id)

    # Проверяем брал ли уже пользователь пробный
    if user_tg and user_tg[7] == "false":
        # Получаем текущий текст сообщения для редактирования
        if query.message:
            current_text = query.message.text or query.message.caption or ""
            await edit_menu_with_image(
                event=query, text=current_text, reply_markup=user_menu(trial="false")
            )
        return

    # Выдаём пробный доступ (1 день). Сервис гарантирует, что пользователь
    # попадёт в нужную группу Pasarguard (по умолчанию "main").
    try:
        user_marz = await subscription_service.grant(
            user_id=user_id,
            days=1,
            note=f"{query.from_user.first_name} @{query.from_user.username}",
        )
    except (SubscriptionError, MarzbanAPIError) as e:
        logger.error(f"Не удалось выдать пробный доступ пользователю {user_id}: {e}")
        return

    # Пользователь уже получил trial
    await db_manage.update_user(user_id, trial="false")

    full_url = get_full_subscription_url(user_marz.subscription_url)
    text = _("trial_days_text", full_url=full_url)
    await edit_menu_with_image(
        event=query, text=text, reply_markup=user_menu(trial="false")
    )
