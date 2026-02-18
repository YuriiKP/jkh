import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile
from dotenv import load_dotenv
from locales import Locales
from middleware import MyLocalesMiddleware
from storage import DB_M
from utils.marzban_api import MarzbanAPIClient

logging.basicConfig(level=logging.INFO)

load_dotenv()


# Настройки подключения к Marzban
PASARGUARD_BASE_URL = os.getenv("PASARGUARD_BASE_URL", "").rstrip("/")
PASARGUARD_ADMIN_USERNAME = os.getenv("PASARGUARD_ADMIN_USERNAME")
PASARGUARD_ADMIN_PASSWORD = os.getenv("PASARGUARD_ADMIN_PASSWORD")


# Тг бот
TG_TOKEN = os.getenv("TG_TOKEN")
TG_ADMIN = os.getenv("TG_ADMIN")
SQLALCHEMY_DATABASE_URL_TG = os.getenv("SQLALCHEMY_DATABASE_URL_TG")

YOO_KASSA_PROVIDER_TOKEN = os.getenv("YOO_KASSA_PROVIDER_TOKEN")

# Webhook (опционально)
BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH") or ""
WEB_SERVER_HOST = os.getenv("WEB_SERVER_HOST", "127.0.0.1")
WEB_SERVER_PORT = int(os.getenv("WEB_SERVER_PORT", "8080"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# Pasarguard notifications (опционально)
# Если переменная не задана/пустая — ручка уведомлений не поднимается, запуск без http-сервера.
PASARGUARD_NOTIFY_PATH = (os.getenv("PASARGUARD_NOTIFY_PATH") or "").strip()
PASARGUARD_NOTIFY_SECRET = os.getenv("PASARGUARD_NOTIFY_SECRET")

bot = Bot(TG_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Инициализация базы данных
db_manage = DB_M(SQLALCHEMY_DATABASE_URL_TG)

# Глобальный клиент Marzban API
marzban_client = MarzbanAPIClient(
    base_url=PASARGUARD_BASE_URL,
    admin_username=PASARGUARD_ADMIN_USERNAME,
    admin_password=PASARGUARD_ADMIN_PASSWORD,
)


# Создаем контекст для локализации и регистрируем мидлвару
locale = Locales()
locale_middleware = MyLocalesMiddleware(locale, db_manage)
dp.update.middleware(locale_middleware)


deep_links_admin_manage = {}


MENU_IMAGE = ""


async def load_menu_image():
    """
    Загружает изображение меню и сохраняет его file_id.
    Вызывается при первом запуске бота.
    """
    global MENU_IMAGE

    if MENU_IMAGE:
        return MENU_IMAGE

    try:
        # Путь к изображению меню
        image_path = os.path.join(os.path.dirname(__file__), "images", "menu.jpg")

        # Проверяем существование файла
        if not os.path.exists(image_path):
            logging.error(f"Изображение меню не найдено: {image_path}")
            return None

        # Определяем chat_id для отправки изображения
        # Если TG_ADMIN установлен, отправляем администратору, иначе отправляем самому себе
        chat_id = TG_ADMIN if TG_ADMIN else None

        # Если TG_ADMIN не установлен, попробуем отправить в чат бота с самим собой
        if not chat_id:
            try:
                # Получаем информацию о боте
                bot_info = await bot.get_me()
                chat_id = bot_info.id
            except Exception as e:
                logging.error(f"Ошибка получения информации о боте: {e}")
                return None

        # Отправляем изображение для получения file_id
        with open(image_path, "rb") as photo_file:
            photo_bytes = photo_file.read()
            photo = BufferedInputFile(photo_bytes, filename="menu.jpg")
            message = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption="Загрузка изображения меню...",
            )

        # Сохраняем file_id изображения
        if message.photo:
            MENU_IMAGE = message.photo[-1].file_id
        else:
            logging.error("В сообщении нет фото")
            return None
        logging.info(f"Изображение меню загружено успешно. File ID: {MENU_IMAGE}")

        # Пытаемся удалить тестовое сообщение, чтобы не засорять чат
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
            logging.info("Тестовое сообщение удалено успешно")
        except Exception as e:
            logging.warning(f"Не удалось удалить тестовое сообщение: {e}")

        return MENU_IMAGE

    except Exception as e:
        logging.error(f"Ошибка загрузки изображения меню: {e}")
        return None


symbols = (
    "a",
    "b",
    "c",
    "d",
    "e",
    "f",
    "g",
    "h",
    "i",
    "j",
    "k",
    "l",
    "m",
    "n",
    "o",
    "p",
    "q",
    "r",
    "s",
    "t",
    "u",
    "v",
    "w",
    "x",
    "y",
    "z",
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
)


def get_full_subscription_url(subscription_url: str) -> str:
    """
    Преобразует относительную ссылку на подписку в полную ссылку с PASARGUARD_BASE_URL.

    :param subscription_url: Относительная ссылка вида /sub/... или полная ссылка
    :return: Полная ссылка с базовым URL
    """
    if not subscription_url:
        return subscription_url

    # Если ссылка уже полная (начинается с http:// или https://), возвращаем как есть
    if subscription_url.startswith(("http://", "https://")):
        return subscription_url

    # Если ссылка относительная (начинается с /), добавляем базовый URL
    if subscription_url.startswith("/"):
        return f"{PASARGUARD_BASE_URL}{subscription_url}"

    # Если ссылка не начинается с /, добавляем базовый URL и /
    return f"{PASARGUARD_BASE_URL}/{subscription_url}"
