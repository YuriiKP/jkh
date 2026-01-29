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
    PASARGUARD_NOTIFY_PATH,
    PASARGUARD_NOTIFY_SECRET,
)
from handlers import dp, bot

from notification_webhook import register_pasarguard_notification_route


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
        if WEBHOOK_PATH:
            await bot.set_webhook(
                url=webhook_url,
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=True,
            )

    async def on_shutdown(_: web.Application) -> None:
        if WEBHOOK_PATH:
            await bot.delete_webhook(drop_pending_updates=False)
        await bot.session.close()

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # Ручка для уведомлений от панели (только если путь задан)
    if PASARGUARD_NOTIFY_PATH:
        register_pasarguard_notification_route(
            app,
            db_manage=db_manage,
            bot=bot,
            notify_path=PASARGUARD_NOTIFY_PATH,
            notify_secret=PASARGUARD_NOTIFY_SECRET,
        )

    # Telegram webhook — только если включен
    if WEBHOOK_PATH:
        SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=WEBHOOK_SECRET,
        ).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
    return app


async def _run_polling():
    """
    Запуск бота в режиме лонг-поллинга.
    Выполняется внутри единственного события asyncio.run.
    """
    await bot.delete_webhook(drop_pending_updates=True)
    await db_manage.create_tables()
    await dp.start_polling(bot)
    await bot.session.close()


def main():
    # Если WEBHOOK_PATH передан — запускаемся на вебхуке (aiohttp сам управляет циклом событий),
    # иначе — на лонг-поллинге через asyncio.run.
    if WEBHOOK_PATH:
        app = _build_webhook_app()
        web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)
    else:
        # Если задан PASARGUARD_NOTIFY_PATH — поднимаем aiohttp для приема уведомлений,
        # иначе — обычный запуск (только long-polling).
        if PASARGUARD_NOTIFY_PATH:
            async def _run_polling_with_http():
                app = _build_webhook_app()
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)
                await site.start()
                try:
                    await _run_polling()
                finally:
                    await runner.cleanup()

            asyncio.run(_run_polling_with_http())
        else:
            asyncio.run(_run_polling())


if __name__ == '__main__':
    main()