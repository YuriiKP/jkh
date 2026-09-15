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
    subscription_service,
)
from locales import get_text as _
from utils.marzban_api import MarzbanAPIError
from utils.subscription import SubscriptionError

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

        await message.answer(text=_("admin_congratulations", status_user=status_user))

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

        # Выдаём/продлеваем подписку. Сервис гарантирует, что пользователь
        # попадёт в нужную группу Pasarguard (по умолчанию "main").
        try:
            await subscription_service.grant(
                user_id=user_id,
                days=deep_link_info.duration_days,
                note=f"{message.from_user.first_name} @{message.from_user.username}",
            )
        except (SubscriptionError, MarzbanAPIError) as e:
            # Не удалось выдать доступ — логируем и продолжаем обычный старт
            print(f"Subscription error: {e}")
            await process_start_bot(message, user_id)
            return

        # Обновляем поле trial в таблице users (если нужно)
        user_tg = await db_manage.get_user_by_id(user_id)
        if user_tg and user_tg[7] == "true":
            await db_manage.update_user(user_id, trial="false")

        await message.answer(
            text=_("admin_subscription_activated", days=deep_link_info.duration_days)
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

        await msg_obj.answer(text=_("rules_text"), reply_markup=rules_menu())

        return

    # Проверяем, принял ли пользователь правила
    if not user[8]:  # rules_accepted находится на 8-й позиции (индекс 8)
        # Нужен объект Message
        if isinstance(message, CallbackQuery):
            msg_obj = message.message
        else:
            msg_obj = message

        await msg_obj.answer(text=_("rules_text"), reply_markup=rules_menu())
        return

    # Нужен объект Message
    if isinstance(message, CallbackQuery):
        msg_obj = message.message
    else:
        msg_obj = message

    await bot.set_my_commands(commands=user_commands, scope=BotCommandScopeDefault())

    menu_keyboards = {
        "user": user_menu(user[7]),
        "admin": admin_menu(),
        "main_admin": main_admin_menu(),
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

        return _(
            "admin_statistics_text",
            total_user=stats.total_user,
            online_users=stats.online_users,
            active_users=stats.active_users,
            on_hold_users=stats.on_hold_users,
            disabled_users=stats.disabled_users,
            expired_users=stats.expired_users,
            limited_users=stats.limited_users,
            version=stats.version,
            cpu_usage=stats.cpu_usage,
            cpu_cores=stats.cpu_cores,
            mem_used_gb=mem_used_gb,
            mem_total_gb=mem_total_gb,
            mem_percent=mem_percent,
            incoming_gb=incoming_gb,
            outgoing_gb=outgoing_gb,
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

    text = _("start_help_message")

    # Отправляем меню с изображением
    await edit_menu_with_image(
        event=msg_obj, text=text, reply_markup=user_menu(str(user[7]))
    )
