from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from utils import delete_old_messages, send_clean_message
from database import db_get_user, db_get_global_stats
from keyboards import main_kb
from config import CURRENCY_NAME

async def cmd_start(message: types.Message, state: FSMContext, bot: Bot):
    await delete_old_messages(message.chat.id, state, bot)
    await state.clear()
    
    await db_get_user(message.from_user.id)
    users_count, tasks_today = await db_get_global_stats()
    
    await send_clean_message(
        message, state, bot,
        f"👋 <b>Добро пожаловать в Mutual!</b>\n\n"
        f"📊 <b>Статистика бота:</b>\n"
        f"👥 Активных пользователей: <b>{users_count}</b>\n"
        f"✅ Выполнено заданий сегодня: <b>{tasks_today}</b>\n\n"
        f"Биржа подписчиков, просмотров и реакций за валюту <b>{CURRENCY_NAME}</b>.\n\n"
        f"💰 Зарабатывайте {CURRENCY_NAME} выполняя задания\n"
        f"📢 Продвигайте свои каналы за {CURRENCY_NAME}\n\n",       
         reply_markup=main_kb 
    )

def register_main_menu_handlers(dp: Dispatcher, bot: Bot):
    @dp.message(Command("start"), F.chat.type.in_({"group", "supergroup"}), StateFilter("*"))
    async def cleanup_group_start(message: types.Message):
        try:
            await message.delete()
        except Exception:
            pass 

    @dp.message(Command("start"), F.chat.type == "private", StateFilter("*"))
    async def cmd_start_handler(message: types.Message, state: FSMContext):
        await cmd_start(message, state, bot)

    @dp.message(F.text == "💰 Заработать", StateFilter("*"))
    async def cmd_earn(message: types.Message, state: FSMContext):
        from handlers.earn import show_earn_menu
        await delete_old_messages(message.chat.id, state, bot)
        await state.clear()
        await show_earn_menu(message, state, bot)

    @dp.message(F.text == "📢 Рекламировать", StateFilter("*"))
    async def cmd_advertise_menu(message: types.Message, state: FSMContext):
        from keyboards import get_ads_menu_kb
        await delete_old_messages(message.chat.id, state, bot)
        await state.clear()
        await send_clean_message(message, state, bot, "📢 <b>Раздел рекламы</b>", reply_markup=get_ads_menu_kb())

    @dp.message(F.text == "👤 Кабинет", StateFilter("*"))
    async def cmd_profile(message: types.Message, state: FSMContext):
        from keyboards import get_deposit_kb
        await delete_old_messages(message.chat.id, state, bot)
        await state.clear()
        
        balance, earned_balance = await db_get_user(message.from_user.id)
        total = balance + earned_balance
        
        await send_clean_message(
            message, state, bot,
            f"👤 <b>Ваш кабинет</b>\n\n"
            f"🆔 ID: <code>{message.from_user.id}</code>\n"
            f"💳 Пополнено: <b>{int(balance)} {CURRENCY_NAME}</b>\n"
            f"⚒️ Заработано: <b>{int(earned_balance)} {CURRENCY_NAME}</b>\n"
            f"💰 Всего: <b>{int(total)} {CURRENCY_NAME}</b>\n\n"
            f"Пополнить баланс можно через Telegram Stars.",
            reply_markup=get_deposit_kb()
        )

    @dp.message(F.text == "📖 Инструкция", StateFilter("*"))
    async def cmd_instruction(message: types.Message, state: FSMContext):
        await delete_old_messages(message.chat.id, state, bot)
        await state.clear()
        
        await send_clean_message(
            message, state, bot,
            "📖 <b>Инструкция</b>\n\n"
            "https://teletype.in/@alexey35w/Ae3S3RBC1YQ",
            reply_markup=main_kb
        )

    @dp.message(F.text == "📋 Условия", StateFilter("*"))
    async def cmd_conditions(message: types.Message, state: FSMContext):
        await delete_old_messages(message.chat.id, state, bot)
        await state.clear()
        
        await send_clean_message(
            message, state, bot,
            "📋 <b>Условия</b>\n\n"
            "https://teletype.in/@alexey35w/IU1uEvhIpHQ",
            reply_markup=main_kb
        )

