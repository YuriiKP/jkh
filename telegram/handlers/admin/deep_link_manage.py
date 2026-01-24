from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.deep_linking import create_start_link
from aiogram import F

from loader import dp, bot, db_manage
from keyboards import *
from filters import IsMainAdmin
from utils.states import StateCreateDeepLink


# Меню создания диплинка подписки
@dp.message(F.text == btn_create_deep_link, IsMainAdmin())
async def deep_link_menu(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(StateCreateDeepLink.days)
    
    await message.answer(
        text='Введите количество дней подписки (целое число):',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Отмена', callback_data='cancel_deep_link')]
        ])
    )
    

# Обработка отмены
@dp.callback_query(F.data == 'cancel_deep_link', IsMainAdmin())
async def cancel_deep_link(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await query.message.edit_text('Создание диплинка отменено.')


# Получение количества дней и генерация диплинка
@dp.message(StateCreateDeepLink.days, IsMainAdmin())
async def process_deep_link_days(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer('Пожалуйста, введите положительное целое число.')
        return
    
    # Генерируем уникальный deep_link
    deep_link_str = await db_manage.create_deep_link(days)
    
    # Создаем стартовую ссылку
    start_link = await create_start_link(
        bot=bot,
        payload=deep_link_str
    )
    
    await state.clear()
    await message.answer(
        text=f'✅ Диплинк подписки на <b>{days}</b> дней создан.\n\n'
             f'Ссылка для активации:\n<code>{start_link}</code>\n\n'
             f'Диплинк: <code>{deep_link_str}</code>\n'
             f'Одноразовый, после активации станет неактивным.',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_main_menu, callback_data='start')]
        ])
    )


# Просмотр списка созданных диплинков (опционально)
@dp.callback_query(F.data == 'list_deep_links', IsMainAdmin())
async def list_deep_links_handler(query: CallbackQuery):
    deep_links = await db_manage.list_deep_links()
    if not deep_links:
        await query.message.answer('Нет созданных диплинков.')
        return
    
    text_lines = ['<b>Список диплинков подписки:</b>\n']
    for dl in deep_links:
        status = '🟢 Активен' if dl.is_active else '🔴 Использован'
        activated = f", активирован пользователем {dl.activated_by_user_id}" if dl.activated_at else ""
        text_lines.append(
            f"• <code>{dl.deep_link}</code> — {dl.duration_days} дней ({status}){activated}"
        )
    
    await query.message.answer('\n'.join(text_lines))