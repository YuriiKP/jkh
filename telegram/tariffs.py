"""
Единая настройка тарифов.

Всё, что относится к тарифам (срок, цены, группа Pasarguard, текст кнопки),
описано в одном месте — здесь. Добавление нового тарифа обычно сводится
к одной записи в `TARIFFS` + тексту кнопки в локалях.

Пример добавления тарифа на 12 месяцев в отдельную группу:

    Tariff(
        key="twelve_months",
        title="12 месяцев",
        days=365,
        rub=int(os.getenv("PRICE_12M_RUB", "1500")),
        stars=int(os.getenv("PRICE_12M_STARS", "820")),
        label_key="btn_buy_twelve_months",
        group="main",
    ),
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Группа Pasarguard по умолчанию: в неё попадает пользователь после оплаты,
# если для тарифа не указана отдельная группа.
DEFAULT_GROUP_NAME = os.getenv("DEFAULT_GROUP_NAME", "main")

# Префикс callback_data кнопок выбора тарифа (btn_buy_<key>).
CALLBACK_PREFIX = "btn_buy_"


@dataclass(frozen=True)
class Tariff:
    """Описание одного тарифа."""

    key: str  # идентификатор тарифа (invoice payload / callback_data)
    title: str  # короткое название для счетов и описаний
    days: int  # срок подписки в днях
    rub: int  # цена в рублях (ЮKassa)
    stars: int  # цена в звёздах (Telegram Stars)
    label_key: str  # ключ локализации текста кнопки покупки
    group: str = DEFAULT_GROUP_NAME  # группа Pasarguard для выдачи доступа

    @property
    def callback(self) -> str:
        """callback_data кнопки покупки этого тарифа."""
        return f"{CALLBACK_PREFIX}{self.key}"


# Тарифы. Порядок в кортеже = порядок кнопок в меню покупки.
TARIFFS: tuple[Tariff, ...] = (
    Tariff(
        key="one_month",
        title="1 месяц",
        days=30,
        rub=int(os.getenv("PRICE_1M_RUB", "150")),
        stars=int(os.getenv("PRICE_1M_STARS", "83")),
        label_key="btn_buy_one_month",
    ),
    Tariff(
        key="three_months",
        title="3 месяца",
        days=90,
        rub=int(os.getenv("PRICE_3M_RUB", "428")),
        stars=int(os.getenv("PRICE_3M_STARS", "236")),
        label_key="btn_buy_three_months",
    ),
    Tariff(
        key="six_months",
        title="6 месяцев",
        days=180,
        rub=int(os.getenv("PRICE_6M_RUB", "810")),
        stars=int(os.getenv("PRICE_6M_STARS", "446")),
        label_key="btn_buy_six_months",
    ),
)

_BY_KEY: dict[str, Tariff] = {tariff.key: tariff for tariff in TARIFFS}
DEFAULT_TARIFF: Tariff = TARIFFS[0]


def get_tariff(key: str | None) -> Tariff:
    """Возвращает тариф по ключу (или тариф по умолчанию, если ключ неизвестен)."""
    return _BY_KEY.get(key or "", DEFAULT_TARIFF)


def tariff_from_callback(callback_data: str | None) -> Tariff:
    """Возвращает тариф по callback_data кнопки покупки."""
    key = (callback_data or "").removeprefix(CALLBACK_PREFIX)
    return get_tariff(key)
