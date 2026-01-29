import os 
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from dotenv import load_dotenv, find_dotenv

from utils.marzban_api import MarzbanAPIClient

from storage import DB_M



logging.basicConfig(level=logging.INFO)

load_dotenv()


# Настройки подключения к Marzban
PASARGUARD_BASE_URL = os.getenv('PASARGUARD_BASE_URL', '').rstrip('/')
PASARGUARD_ADMIN_USERNAME = os.getenv('PASARGUARD_ADMIN_USERNAME')
PASARGUARD_ADMIN_PASSWORD = os.getenv('PASARGUARD_ADMIN_PASSWORD')


# Тг бот
TG_TOKEN = os.getenv('TG_TOKEN')
TG_ADMIN = os.getenv('TG_ADMIN')
SQLALCHEMY_DATABASE_URL_TG = os.getenv('SQLALCHEMY_DATABASE_URL_TG')

YOO_KASSA_PROVIDER_TOKEN = os.getenv('YOO_KASSA_PROVIDER_TOKEN')

# Webhook (опционально)
BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL")
WEBHOOK_PATH = (os.getenv("WEBHOOK_PATH") or "")
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


deep_links_admin_manage = {}

symbols = (
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n',
    'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', '0', '1', 
    '2', '3', '4', '5', '6', '7', '8', '9'
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
    if subscription_url.startswith(('http://', 'https://')):
        return subscription_url
    
    # Если ссылка относительная (начинается с /), добавляем базовый URL
    if subscription_url.startswith('/'):
        return f"{PASARGUARD_BASE_URL}{subscription_url}"
    
    # Если ссылка не начинается с /, добавляем базовый URL и /
    return f"{PASARGUARD_BASE_URL}/{subscription_url}"