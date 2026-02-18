import json
from contextvars import ContextVar
from pathlib import Path

import yaml

_current_locales = ContextVar("current_locales", default="en")
_current_lang = ContextVar("current_lang", default="en")


class Locales:
    def __init__(self):
        self.translations = {}
        self._load_translations()

    def _load_translations(self):
        """Загружаем все yaml файлы из папки"""
        path = Path("locales")
        for file in path.glob("*.yaml"):
            lang = file.stem  # "ru.yaml" → "ru"
            with open(file, encoding="utf-8") as f:
                self.translations[lang] = yaml.safe_load(f)

    def get_text(self, key: str, lang: str, **kwargs) -> str:
        """
        Достать перевод по ключу

        Примеры:
          get_text("welcome", "ru", name="Иван")
          get_text("buttons.profile", "ru")
          get_text("btn.expires", "ru", date="01.01.2025")
        """
        # Берём переводы для языка, если нет — берём английский
        data = self.translations.get(lang) or self.translations.get("en", {})

        # Поддержка вложенных ключей через точку
        # "buttons.profile" → data["buttons"]["profile"]
        value = data
        for part in key.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
                break

        # Если ключ не найден — возвращаем сам ключ
        if value is None:
            return key

        return value.format(**kwargs) if kwargs else value


def setup_context(locales: Locales, lang: str):
    """Вызывается мидлварой для установки контекста"""
    _current_locales.set(locales)
    _current_lang.set(lang)


def get_text(key: str, **kwargs) -> str:
    """Главная функция для получения перевода"""
    locales: Locales = _current_locales.get()
    lang = _current_lang.get()
    return locales.get_text(key, lang, **kwargs)
