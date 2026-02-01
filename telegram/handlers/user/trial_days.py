from datetime import datetime, timedelta

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from keyboards import help_menu, trial_days_text, user_menu
from loader import db_manage, dp, marzban_client
from models.proxy import ProxyTable, VlessSettings, XTLSFlows
from models.user import UserCreate, UserResponse, UserStatusCreate
from utils.marzban_api import MarzbanAPIError

from ..common import edit_menu_with_image


# Обработчик кнопки "Пробный период"
@dp.callback_query(F.data == "trial_bay")
async def trial_buy_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    user_id = query.from_user.id
    user_tg = await db_manage.get_user_by_id(user_id)

    # Проверяем брал ли уже пользователь пробный
    if user_tg and user_tg[7] == "false":
        # Получаем текущий текст сообщения для редактирования
        if query.message:
            current_text = query.message.text or query.message.caption or ""
            await edit_menu_with_image(
                event=query, text=current_text, reply_markup=user_menu(trial="false")
            )
        return

    # Если пользователя в marzban нет создаем его
    try:
        user_marz: UserResponse = await marzban_client.get_user(str(user_id))
    except MarzbanAPIError as e:
        if e.status == 404:
            # Ошибка в панели, on_hold корректно вообще не работает
            # new_user = UserCreate(
            #     username=str(user_id),
            #     note=f'{query.from_user.first_name} @{query.from_user.username}',
            #     status=UserStatusCreate.on_hold,
            #     on_hold_expire_duration=86400 * 3,  # 3 дня в секундах
            #     group_ids=[1],
            #     proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION))
            # )

            new_user = UserCreate(
                username=str(user_id),
                note=f"{query.from_user.first_name} @{query.from_user.username}",
                status=UserStatusCreate.active,
                expire=datetime.now() + timedelta(3.0),
                group_ids=[1],
                proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION)),
            )
            user_marz: UserResponse = await marzban_client.create_user(new_user)

        else:
            print(e.message)

    # Пользователь уже получил trial
    await db_manage.update_user(user_id, trial="false")

    if user_marz:
        text = trial_days_text(user_marz.subscription_url)
        await edit_menu_with_image(
            event=query, text=text, reply_markup=user_menu(trial="false")
        )
