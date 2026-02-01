from datetime import datetime, timedelta

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommandScopeDefault,
    CallbackQuery,
    Message,
)
from commands import user_commands
from keyboards import *
from loader import (
    bot,
    db_manage,
    deep_links_admin_manage,
    dp,
    marzban_client,
)
from models.proxy import ProxyTable, VlessSettings, XTLSFlows
from models.user import UserCreate, UserModify, UserStatusCreate, UserStatusModify
from utils.marzban_api import MarzbanAPIError

from .common import edit_menu_with_image


# Старт с диплинком
@dp.message(CommandStart(deep_link=True))
async def process_start_bot_deep_link(
    message: Message, state: FSMContext, command: CommandObject
):
    await state.clear()

    args = command.args

    # 1. Проверяем админские диплинки (временные)
    if args and args in deep_links_admin_manage:
        status_user = deep_links_admin_manage[args]
        del deep_links_admin_manage[args]

        await db_manage.update_user(
            user_id=message.from_user.id, status_user=status_user
        )

        await message.answer(text=f"Поздравляю! Теперь ты {status_user}")

        await process_start_bot(message, message.from_user.id)
        return

    # 2. Проверяем диплинки подписки в БД
    if not args:
        await process_start_bot(message, message.from_user.id)
        return

    deep_link_info = await db_manage.get_deep_link(args)
    if deep_link_info is not None:
        # Диплинк активен, активируем подписку
        user_id = message.from_user.id

        # Активируем диплинк (помечаем использованным)
        success = await db_manage.activate_deep_link(args, user_id)
        if not success:
            # Что-то пошло не так (возможно, уже использован)
            await process_start_bot(message, user_id)
            return

        # Продлеваем подписку пользователя через Marzban
        try:
            user_marz = await marzban_client.get_user(str(user_id))
            # Определяем текущую дату истечения
            if user_marz.expire:
                # Если expire это timestamp (int), конвертируем в datetime
                if isinstance(user_marz.expire, int):
                    current_expire = datetime.fromtimestamp(user_marz.expire)
                else:
                    current_expire = user_marz.expire
                    # Если datetime имеет timezone, конвертируем в naive datetime
                    if current_expire.tzinfo is not None:
                        current_expire = current_expire.replace(tzinfo=None)
            else:
                # Если подписки нет, начинаем с текущей даты
                current_expire = datetime.now()

            # Добавляем дни из диплинка
            new_expire = current_expire + timedelta(days=deep_link_info.duration_days)

            modify_user = UserModify(
                expire=new_expire,
                proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION)),
                status=UserStatusModify.active,
            )
            user_marz = await marzban_client.modify_user(str(user_id), modify_user)
        except MarzbanAPIError as e:
            if e.status == 404:
                # Пользователя нет в Marzban, создаем нового
                new_user = UserCreate(
                    username=str(user_id),
                    note=f"{message.from_user.first_name} @{message.from_user.username}",
                    status=UserStatusCreate.active,
                    expire=datetime.now()
                    + timedelta(days=deep_link_info.duration_days),
                    group_ids=[1],
                    proxy_settings=ProxyTable(
                        vless=VlessSettings(flow=XTLSFlows.VISION)
                    ),
                )
                user_marz = await marzban_client.create_user(new_user)
            else:
                # Ошибка API, логируем и продолжаем обычный старт
                print(f"Marzban API error: {e.message}")
                await process_start_bot(message, user_id)
                return

        # Обновляем поле trial в таблице users (если нужно)
        user_tg = await db_manage.get_user_by_id(user_id)
        if user_tg and user_tg[7] == "true":
            await db_manage.update_user(user_id, trial="false")

        await message.answer(
            text=f"✅ Подписка активирована! Добавлено {deep_link_info.duration_days} дней."
        )
        await process_start_bot(message, user_id)
        return

    # 3. Если диплинк не найден, обычный старт
    await process_start_bot(message, message.from_user.id)


# Обычный старт
@dp.message(CommandStart())
async def start_command(message: Message, state: FSMContext):
    await state.clear()

    await process_start_bot(message, message.from_user.id)


# Старт с колбэка
@dp.callback_query(F.data == "start")
async def inline_process_start_bot(query: CallbackQuery, state: FSMContext):
    await state.clear()

    # await query.message.delete()
    await state.clear()
    await process_start_bot(query, query.from_user.id)


# Функция запуска
async def process_start_bot(message: Message | CallbackQuery, user_id: str | int):
    user = await db_manage.get_user_by_id(user_id)

    if user is None:
        # Получаем объект пользователя в зависимости от типа message
        if isinstance(message, CallbackQuery):
            from_user = message.from_user
            msg_obj = message.message
        else:
            from_user = message.from_user
            msg_obj = message

        await db_manage.add_new_user(
            from_user.id,
            from_user.username or "",
            from_user.first_name or "",
            from_user.last_name or "",
            language=from_user.language_code or "ru",
        )

        await msg_obj.answer(text=rules_text, reply_markup=rules_menu())

        return

    # Нужен объект Message
    if isinstance(message, CallbackQuery):
        msg_obj = message.message
    else:
        msg_obj = message

    await bot.set_my_commands(commands=user_commands, scope=BotCommandScopeDefault())

    menu_keyboards = {
        "user": user_menu(user[7]),
        "admin": admin_menu,
        "main_admin": main_admin_menu,
    }

    # Для админ-статистики
    async def get_admin_text():
        stats = await marzban_client.system_stats()
        mem_used_gb = stats.mem_used / (1024**3)
        mem_total_gb = stats.mem_total / (1024**3)
        mem_percent = (
            (stats.mem_used / stats.mem_total) * 100 if stats.mem_total > 0 else 0
        )
        incoming_gb = stats.incoming_bandwidth / (1024**3)
        outgoing_gb = stats.outgoing_bandwidth / (1024**3)

        return (
            f"📊 <b>Статистика сервера</b>:\n\n"
            f"👥 <b>Пользователи</b>:\n"
            f"  • Всего: {stats.total_user}\n"
            f"  • Онлайн: {stats.online_users}\n"
            f"  • Активные: {stats.active_users}\n"
            f"  • На паузе: {stats.on_hold_users}\n"
            f"  • Отключены: {stats.disabled_users}\n"
            f"  • Истекли: {stats.expired_users}\n"
            f"  • Ограничены: {stats.limited_users}\n\n"
            f"💻 <b>Система</b>:\n"
            f"  • Версия: {stats.version}\n"
            f"  • CPU: {stats.cpu_usage:.1f}% ({stats.cpu_cores} ядер)\n"
            f"  • RAM: {mem_used_gb:.2f} GB / {mem_total_gb:.2f} GB ({mem_percent:.1f}%)\n\n"
            f"📡 <b>Трафик</b>:\n"
            f"  • Входящий: {incoming_gb:.2f} GB\n"
            f"  • Исходящий: {outgoing_gb:.2f} GB"
        )

    status = user[5] if user else None

    # Определяем клавиатуру и текст
    if (
        status in ("admin", "main_admin")
        and isinstance(msg_obj, Message)
        and msg_obj.text == "/start"
    ):
        keyboard = menu_keyboards[status]
        text_admin = await get_admin_text()

        await msg_obj.answer(text=text_admin, reply_markup=keyboard)

    text = start_help_message

    # Отправляем меню с изображением
    await edit_menu_with_image(
        event=msg_obj, text=text, reply_markup=user_menu(str(user[7]))
    )
