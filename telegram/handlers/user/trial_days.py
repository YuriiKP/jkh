from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram import F

from models.user import UserResponse, UserCreate, UserStatusCreate
from utils.marzban_api import MarzbanAPIError

from loader import dp, db_manage, marzban_client
from keyboards import user_menu, help_menu, trial_days_text



# Обработчик кнопки "Пробный период"
@dp.callback_query(F.data == 'trial_bay')
async def trial_buy_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    
    user_id = query.from_user.id
    user_tg = await db_manage.get_user_by_id(user_id)

    # Проверяем брал ли уже пользователь пробный
    if user_tg[7] == 'false':
        await query.message.edit_reply_markup(
            reply_markup=user_menu(trial='false')
        )
        return
    
    # Если пользователя в marzban нет создаем его
    try:
        user_marz: UserResponse = await marzban_client.get_user(user_id)
    except MarzbanAPIError as e:
        if e.status == 404:
            new_user = UserCreate(
                username=str(user_id),
                note=f'{query.from_user.first_name} @{query.from_user.username}',
                status=UserStatusCreate.on_hold,
                on_hold_expire_duration=86400 * 3,  # 3 дня в секундах
                inbounds={},
                proxies={
                    'vless': {'flow': 'xtls-rprx-vision'}
                }
            )
            user_marz: UserResponse = await marzban_client.create_user(new_user)
        
        else: 
            print(e.message)
    
    # Пользователь уже получил trial 
    await db_manage.update_user(user_id, trial='false')
    
    text = trial_days_text(user_marz.subscription_url)
    await query.message.edit_text(
        text=text,
        reply_markup=user_menu(trial='false')
    )
        
    