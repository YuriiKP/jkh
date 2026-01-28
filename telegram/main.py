import asyncio

from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from loader import (
    dp,
    bot,
    db_manage,
    BASE_WEBHOOK_URL,
    WEB_SERVER_HOST,
    WEB_SERVER_PORT,
    WEBHOOK_PATH,
    WEBHOOK_SECRET,
)
from handlers import dp, bot



def _join_url(base: str, path: str) -> str:
    base = (base or "").rstrip("/")
    path = (path or "").strip()
    if not path.startswith("/"):
        path = f"/{path}" if path else ""
    return f"{base}{path}"


def _build_webhook_app() -> web.Application:
    app = web.Application()

    webhook_url = _join_url(BASE_WEBHOOK_URL, WEBHOOK_PATH)

    async def on_startup(_: web.Application) -> None:
        await db_manage.create_tables()
        await bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True,
        )

    async def on_shutdown(_: web.Application) -> None:
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.session.close()

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)
    return app


async def main():
    # Если WEBHOOK_PATH передан — запускаемся на вебхуке, иначе на лонг-поллинге
    if WEBHOOK_PATH:
        app = _build_webhook_app()
        web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)
        return

    await bot.delete_webhook(drop_pending_updates=True)
    await db_manage.create_tables()
    await dp.start_polling(bot)
    await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main()) 