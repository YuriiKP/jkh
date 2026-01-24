import asyncio

from aiogram import filters 
from aiogram.types import Message

from loader import dp, bot, db_manage
from handlers import dp, bot



async def main():
    await bot.delete_webhook(drop_pending_updates=True)

    await db_manage.create_tables()
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main()) 