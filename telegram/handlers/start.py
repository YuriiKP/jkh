from aiogram.types import Message, CallbackQuery, BotCommandScopeDefault
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram import F
from aiogram.exceptions import TelegramBadRequest

from loader import dp, bot, deep_links_admin_manage, db_manage, marzban_client
from models.user import UserCreate, UserStatusCreate, UserModify, UserStatusModify
from models.proxy import ProxyTable, VlessSettings, XTLSFlows
from utils.marzban_api import MarzbanAPIError
from keyboards import *
from filters import IsAdmin, IsMainAdmin, IsUser
from commands import user_commands
    


# Старт с диплинком
@dp.message(CommandStart(deep_link=True))
async def process_start_bot_deep_link(message: Message, state: FSMContext, command: CommandObject):
    await state.clear()

    args = command.args
    
    # 1. Проверяем админские диплинки (временные)
    if args in deep_links_admin_manage:
        status_user = deep_links_admin_manage[args]
        del deep_links_admin_manage[args]

        await db_manage.update_user(
            user_id=message.from_user.id,
            status_user=status_user
        )

        await message.answer(
            text=f'Поздравляю! Теперь ты {status_user}'
        )

        await process_start_bot(message, message.from_user.id, message.from_user.first_name)
        return
    
    # 2. Проверяем диплинки подписки в БД
    deep_link_info = await db_manage.get_deep_link(args)
    if deep_link_info is not None:
        # Диплинк активен, активируем подписку
        user_id = message.from_user.id
        duration_seconds = deep_link_info.duration_days * 86400
        
        # Активируем диплинк (помечаем использованным)
        success = await db_manage.activate_deep_link(args, user_id)
        if not success:
            # Что-то пошло не так (возможно, уже использован)
            await process_start_bot(message, user_id, message.from_user.first_name)
            return
        
        # Продлеваем подписку пользователя через Marzban
        try:
            user_marz = await marzban_client.get_user(str(user_id))
            # Определяем текущий срок
            if user_marz.expire:
                current_expire = user_marz.expire
            elif user_marz.on_hold_expire_duration:
                current_expire = user_marz.on_hold_expire_duration
            else:
                current_expire = 0
            
            modify_user = UserModify(
                on_hold_expire_duration=current_expire + duration_seconds,
                proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION)),
                status=UserStatusModify.on_hold
            )
            user_marz: UserResponse = await marzban_client.modify_user(str(user_id), modify_user)
        except MarzbanAPIError as e:
            if e.status == 404:
                # Пользователя нет в Marzban, создаем нового
                new_user = UserCreate(
                    username=str(user_id),
                    note=f'{message.from_user.first_name} @{message.from_user.username}',
                    status=UserStatusCreate.on_hold,
                    on_hold_expire_duration=duration_seconds,
                    group_ids=[1],
                    proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION))
                )
                user_marz = await marzban_client.create_user(new_user)
            else:
                # Ошибка API, логируем и продолжаем обычный старт
                print(f"Marzban API error: {e.message}")
                await process_start_bot(message, user_id, message.from_user.first_name)
                return
        
        # Обновляем поле trial в таблице users (если нужно)
        user_tg = await db_manage.get_user_by_id(user_id)
        if user_tg and user_tg[7] == 'true':
            await db_manage.update_user(user_id, trial='false')
        
        await message.answer(
            text=f'✅ Подписка активирована! Добавлено {deep_link_info.duration_days} дней.'
        )
        await process_start_bot(message, user_id, message.from_user.first_name)
        return
    
    # 3. Если диплинк не найден, обычный старт
    await process_start_bot(message, message.from_user.id, message.from_user.first_name)



# Обычный старт 
@dp.message(CommandStart())
async def start_command(message: Message, state: FSMContext):
    await state.clear()
    
    await db_manage.add_new_user(
        message.from_user.id, 
        message.from_user.username, 
        message.from_user.first_name, 
        message.from_user.last_name,
        language=message.from_user.language_code
        )
    
    await process_start_bot(message, message.from_user.id, message.from_user.first_name)


# Старт с колбэка
@dp.callback_query(F.data == 'start')
async def inline_process_start_bot(query: CallbackQuery, state: FSMContext):
    await state.clear()
    
    # await query.message.delete()
    await state.clear()
    await process_start_bot(query.message, query.from_user.id, query.from_user.first_name)



# Функция запуска
async def process_start_bot(message: Message, user_id, first_name):
    user = await db_manage.get_user_by_id(user_id)
    
    await bot.set_my_commands(
        commands=user_commands,
        scope=BotCommandScopeDefault()
        )

    menu_keyboards = {
        'user': user_menu(user[7]),
        'admin': admin_menu,
        'main_admin': main_admin_menu
    }

    # Для админ-статистики
    async def get_admin_text():
        stats = await marzban_client.system_stats()
        mem_used_gb = stats.mem_used / (1024 ** 3)
        mem_total_gb = stats.mem_total / (1024 ** 3)
        mem_percent = (stats.mem_used / stats.mem_total) * 100 if stats.mem_total > 0 else 0 
        incoming_gb = stats.incoming_bandwidth / (1024 ** 3)
        outgoing_gb = stats.outgoing_bandwidth / (1024 ** 3)

        return (
            f'📊 <b>Статистика сервера</b>:\n\n'
            f'👥 <b>Пользователи</b>:\n'
            f'  • Всего: {stats.total_user}\n'
            f'  • Онлайн: {stats.online_users}\n'
            f'  • Активные: {stats.active_users}\n'
            f'  • На паузе: {stats.on_hold_users}\n'
            f'  • Отключены: {stats.disabled_users}\n'
            f'  • Истекли: {stats.expired_users}\n'
            f'  • Ограничены: {stats.limited_users}\n\n'
            f'💻 <b>Система</b>:\n'
            f'  • Версия: {stats.version}\n'
            f'  • CPU: {stats.cpu_usage:.1f}% ({stats.cpu_cores} ядер)\n'
            f'  • RAM: {mem_used_gb:.2f} GB / {mem_total_gb:.2f} GB ({mem_percent:.1f}%)\n\n'
            f'📡 <b>Трафик</b>:\n'
            f'  • Входящий: {incoming_gb:.2f} GB\n'
            f'  • Исходящий: {outgoing_gb:.2f} GB'
        )


    status = user[5] if user else None

    # Определяем клавиатуру и текст
    if status in ('admin', 'main_admin') and message.text == '/start':
        keyboard = menu_keyboards[status]
        text_admin = await get_admin_text()
        
        await message.answer(
            text=text_admin,
            reply_markup=keyboard
        )
   
    text = start_help_message

    try:
        await message.edit_text(
            text=text,
            reply_markup=user_menu(user[7])
        )
    except TelegramBadRequest:
        await message.answer(
            text=text,
            reply_markup=user_menu(user[7])
        )
        try:
            if message.text != '/start':
                await message.delete()
        except TelegramBadRequest:
            pass  # Игнорируем, если уже удалено