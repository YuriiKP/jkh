from datetime import datetime

from loader import get_full_subscription_url
from locales import get_text as _
from models.user import UserResponse


def my_keys_stat_info(user_marz: UserResponse):
    # Форматируем статус
    status_emoji = {
        "active": "✅",
        "disabled": "❌",
        "limited": "⚠️",
        "expired": "⏰",
        "on_hold": "⏸️",
    }

    emoji = status_emoji.get(user_marz.status.value, "❓")
    status = _(user_marz.status.value)

    # Форматируем трафик
    lifetime_used_gb = user_marz.lifetime_used_traffic / (1024**3)

    # Форматируем дату истечения
    if user_marz.expire == 0:
        expire_text = "∞"
    elif user_marz.expire is not None:
        # Обрабатываем expire как datetime или timestamp (int)
        if isinstance(user_marz.expire, int):
            expire_date = datetime.fromtimestamp(user_marz.expire)
        else:
            expire_date = user_marz.expire
            # Если datetime имеет timezone, конвертируем в naive datetime для сравнения
            if expire_date.tzinfo is not None:
                expire_date = expire_date.replace(tzinfo=None)

        # Вычисляем оставшиеся дни (используем naive datetime для сравнения)
        now = datetime.now()
        remaining_delta = expire_date - now
        remaining_days = remaining_delta.days

        # Форматируем дату и оставшиеся дни
        expire_text = expire_date.strftime("%d.%m.%y | ") + f" ({remaining_days} д.)"
    else:
        expire_text = "На паузе"

    full_subscription_url = get_full_subscription_url(user_marz.subscription_url)

    return _(
        "my_keys_stat_info",
        emoji=emoji,
        status=status,
        lifetime_used_gb=lifetime_used_gb,
        expire_text=expire_text,
        full_subscription_url=full_subscription_url,
    )


def notification_days_left_text(days_left) -> str:
    # Определяем правильное склонение слова "день"
    day_word = "день" if days_left == 1 else "дня"

    return _("notification_days_left_text", days_left=days_left, day_word=day_word)
