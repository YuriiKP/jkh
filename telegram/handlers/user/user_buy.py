from datetime import datetime, timedelta
from aiogram.types import CallbackQuery, Message, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from aiogram import F

from models.user import UserResponse, UserCreate, UserStatusCreate, UserModify, UserStatusModify
from models.proxy import ProxyTable, VlessSettings, XTLSFlows
from utils.marzban_api import MarzbanAPIError

from loader import dp, db_manage, marzban_client, YOO_KASSA_PROVIDER_TOKEN
from keyboards import *


# Обработчик кнопки "Купить"
@dp.callback_query(F.data == 'buy')
async def buy_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()

    try:
        await query.message.edit_text(
            text=user_buy_text,
            reply_markup=buy_menu()
        )
    except TelegramBadRequest:
        # Если нельзя редактировать, отправляем новое сообщение и удаляем старое
        await query.message.answer(
            text=user_buy_text,
            reply_markup=buy_menu()
        )
        try:
            await query.message.delete()
        except TelegramBadRequest:
            pass  # Игнорируем, если уже удалено


@dp.callback_query(F.data == 'btn_buy_one_month')
async def buy_one_month_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    
    # Показываем меню выбора способа оплаты
    try:
        await query.message.edit_text(
            text=payment_method_text,
            reply_markup=user_payment_method_menu()
        )
    except TelegramBadRequest:
        # Если нельзя редактировать, отправляем новое сообщение и удаляем старое
        await query.message.answer(
            text=payment_method_text,
            reply_markup=user_payment_method_menu()
        )
        try:
            await query.message.delete()
        except TelegramBadRequest:
            pass  # Игнорируем, если уже удалено


@dp.callback_query(F.data == 'btn_pay_with_card')
async def pay_with_card_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    
    # Цена в копейках (2 рубля = 200 копеек)
    prices = [LabeledPrice(label="1 месяц VPN", amount=10000)]
    
    # provider_data для ЮKassa с указанием метода оплаты СБП
    # provider_data = '{"payment_method_type": "sbp"}'
    
    # Отправляем инвойс с провайдером ЮKassa
    await query.message.answer_invoice(
        title="Подписка на 1 месяц",
        description="ЖКХ подписка на 30 дней",
        prices=prices,
        payload="one_month",         # id тарифа
        currency="RUB",              # Код валюты для рублёвых платежей
        provider_token=YOO_KASSA_PROVIDER_TOKEN,
        # provider_data=provider_data,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить 100 ₽", pay=True)],
            [InlineKeyboardButton(text="Отмена", callback_data="buy")]
        ])
    )
    
    await query.message.delete()


@dp.callback_query(F.data == 'btn_pay_with_stars')
async def buy_one_month_handler(query: CallbackQuery, state: FSMContext):
    await state.clear()
    
    # 1. Формируем цену
    prices = [LabeledPrice(label="1 месяц VPN", amount=55)] 

    # 2. Отправляем инвойс
    await query.message.answer_invoice(
        title="Подписка на 1 месяц",
        description="ЖКХ подписка на 30 дней",
        prices=prices,
        payload="one_month",         # id тарифа
        currency="XTR",              # Код валюты для звезд тг
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Оплатить 55 ⭐️", pay=True)],
            [InlineKeyboardButton(text="Отмена", callback_data="buy")]
        ])
    )

    await query.message.delete()


# Обработака успешной оплаты
@dp.message(F.successful_payment)
async def success_payment_handler(message: Message):
    payment_info = message.successful_payment
    
    if payment_info.invoice_payload == "one_month":
        user_id = message.from_user.id
        
        # Если есть не активированай пробный период, отменям его
        user_tg = await db_manage.get_user_by_id(user_id)
        if user_tg[7] == 'true':
            await db_manage.update_user(user_id, trial='false')
        
        # Если пользователя в marzban нет создаем его
        try:
            user_marz: UserResponse = await marzban_client.get_user(user_id)
            
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

            # Добавляем 30 дней к текущей дате истечения
            new_expire = current_expire + timedelta(days=30)

            modify_user = UserModify(
                expire=new_expire,
                proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION)),
                status=UserStatusModify.active
            )
            user_marz: UserResponse = await marzban_client.modify_user(user_id, modify_user)
        except MarzbanAPIError as e:
            if e.status == 404:
                new_user = UserCreate(
                    username=str(user_id),
                    note=f'{message.from_user.first_name} @{message.from_user.username}',
                    status=UserStatusCreate.active,
                    expire=datetime.now() + timedelta(days=30),
                    group_ids=[1],
                    proxy_settings=ProxyTable(vless=VlessSettings(flow=XTLSFlows.VISION))
                )
                user_marz: UserResponse = await marzban_client.create_user(new_user)
            
            else: 
                print(e.message)

        # Сохраняем информацию о платеже в базе данных
        await db_manage.add_payment(
            user_id=user_id,
            amount=payment_info.total_amount,
            currency=payment_info.currency,
            payload=payment_info.invoice_payload,
            telegram_payment_charge_id=payment_info.telegram_payment_charge_id,
            provider_payment_charge_id=payment_info.provider_payment_charge_id,
            status='completed'
        )

        await message.answer("Оплата прошла успешно! Ваша подписка обновлена. 🚀")
        await message.answer(
            text=my_keys_stat_info(user_marz),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=
                    [
                        [InlineKeyboardButton(text=btn_how_to_connect, callback_data='how_to_connect')],
                        [InlineKeyboardButton(text=btn_main_menu, callback_data='start')],
                    ]
                )
            )