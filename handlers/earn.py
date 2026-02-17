import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
import database  # <--- Импортируем модуль целиком
from database import (
    db_get_available_counts, db_get_tasks_paginated, 
    db_complete_task_immediate, db_create_review, db_get_review, db_delete_review
    # db_pool УБРАЛИ ОТСЮДА
)
from keyboards import (
    get_earn_menu_kb, get_back_to_earn_menu_kb, get_paginated_kb, 
    get_cancel_kb, main_kb
)
from states import AppStates
from utils import send_clean_message, safe_edit_message
from config import UNSUB_CHECK_DAYS, CURRENCY_NAME
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)

async def show_earn_menu(message_or_call, state: FSMContext, bot: Bot):
    user_id = message_or_call.from_user.id
    
    channels_count, groups_count, views_count, reactions_count, bots_count = await db_get_available_counts(user_id)
    
    text = (
        f"📢 Заданий на каналы: {channels_count}\n"
        f"👥 Заданий на группы: {groups_count}\n"
        f"🤖 Заданий на ботов: {bots_count}\n"
        f"👁️ Заданий на просмотры: {views_count}\n"
        f"❤️ Заданий на реакции: {reactions_count}\n\n"
        f"🔔 Оплата начисляется <b>СРАЗУ</b>.\n"
        f"⚠️ Для подписок работает мониторинг (штраф x2 за отписку).\n"
        f"📷 Для просмотров, реакций и ботов нужна проверка скриншотом."
    )
    
    if isinstance(message_or_call, types.Message):
        await send_clean_message(message_or_call, state, bot, text, reply_markup=get_earn_menu_kb())
    else:
        await safe_edit_message(message_or_call.message, state, bot, text, reply_markup=get_earn_menu_kb())

async def show_earn_list(callback, state: FSMContext, bot: Bot, task_type, page=1):
    per_page = 5
    user_id = callback.from_user.id
    
    tasks, total_count = await db_get_tasks_paginated(user_id, task_type, page, per_page)
    
    type_name_map = {
        "channel": "каналы", 
        "group": "группы", 
        "view": "просмотры", 
        "reaction": "реакции",
        "bot": "боты"
    }
    type_name = type_name_map.get(task_type, "задания")
    
    if total_count == 0:
        text = f"😔 <b>Заданий ({type_name}) пока нет</b>\nПопробуйте зайти позже!"
        kb = get_back_to_earn_menu_kb()
    else:
        desc = "💰 Оплата сразу после проверки."
        if task_type in ['channel', 'group']:
            desc += f"\n🚫 Штраф x2 за отписку ({UNSUB_CHECK_DAYS} дней)."
        else:
            desc += "\n📷 Для проверки потребуется СКРИНШОТ."
        
        text = (
            f"📋 <b>Список заданий ({type_name})</b>\n\n"
            f"{desc}\n"
            "👇 Нажмите кнопку ссылки, затем кнопку подтверждения:"
        )
        kb = get_paginated_kb(tasks, page, total_count, per_page, mode="earn", task_type=task_type)
    
    await safe_edit_message(callback.message, state, bot, text, reply_markup=kb)

def register_earn_handlers(dp: Dispatcher, bot: Bot):
    @dp.callback_query(F.data == "back_to_earn_menu")
    async def back_to_earn_menu_cb(callback: types.CallbackQuery, state: FSMContext):
        await show_earn_menu(callback, state, bot)
        await callback.answer()

    @dp.callback_query(F.data == "earn_channel")
    async def show_earn_channels(callback: types.CallbackQuery, state: FSMContext):
        await show_earn_list(callback, state, bot, "channel", page=1)

    @dp.callback_query(F.data == "earn_group")
    async def show_earn_groups(callback: types.CallbackQuery, state: FSMContext):
        await show_earn_list(callback, state, bot, "group", page=1)

    @dp.callback_query(F.data == "earn_view")
    async def show_earn_views(callback: types.CallbackQuery, state: FSMContext):
        await show_earn_list(callback, state, bot, "view", page=1)

    @dp.callback_query(F.data == "earn_reaction")
    async def show_earn_reactions(callback: types.CallbackQuery, state: FSMContext):
        await show_earn_list(callback, state, bot, "reaction", page=1)

    @dp.callback_query(F.data == "earn_bot")
    async def show_earn_bots(callback: types.CallbackQuery, state: FSMContext):
        await show_earn_list(callback, state, bot, "bot", page=1)

    @dp.callback_query(F.data.startswith("check_"))
    async def process_check_task(callback: types.CallbackQuery, state: FSMContext):
        parts = callback.data.split("_")
        task_id = int(parts[1])
        current_page = int(parts[2]) if len(parts) > 2 else 1
        task_type = parts[3] if len(parts) > 3 else "channel"
        
        # ИСПРАВЛЕНИЕ: используем database.db_pool
        async with database.db_pool.acquire() as conn:
            task_data = await conn.fetchrow("SELECT channel_link, price_per_sub, channel_title FROM tasks WHERE id=$1", task_id)
        
        if not task_data:
            await callback.answer("❌ Задание не найдено", show_alert=True)
            await show_earn_list(callback, state, bot, task_type, current_page)
            return

        # --- ЛОГИКА ДЛЯ ПРОСМОТРОВ, РЕАКЦИЙ И БОТОВ ---
        if task_type in ['view', 'reaction', 'bot']:
            link = task_data['channel_link']
            
            action_text = "просмотра"
            instruction = "Сделайте скриншот поста"
            
            if task_type == 'reaction':
                action_text = "реакции"
                instruction = "Поставьте реакцию и сделайте скриншот"
            elif task_type == 'bot':
                action_text = "запуска"
                instruction = "Запустите бота (Start) и сделайте скриншот"
            
            await send_clean_message(
                callback.message, state, bot,
                f"👁️ <b>Проверка {action_text}</b>\n\n"
                f"1. Перейдите по ссылке: {link}\n"
                f"2. {instruction}\n"
                f"3. <b>Отправьте скриншот сюда</b> в ответ на это сообщение.",
                reply_markup=get_cancel_kb()
            )
            
            await state.update_data(current_task_id=task_id)
            await state.set_state(AppStates.waiting_proof_screenshot)
            await callback.answer()
            return

        # --- ЛОГИКА ДЛЯ ПОДПИСОК ---
        else:
            channel_username = task_data['channel_link'].replace('@', '').replace('https://t.me/', '').strip('/')
            can_complete = False
            try:
                member = await bot.get_chat_member(chat_id=f"@{channel_username}", user_id=callback.from_user.id)
                if member.status in ['member', 'administrator', 'creator']:
                    can_complete = True
            except Exception as e:
                logger.error(f"Check error: {e}")
                await callback.answer("❌ Бот не видит подписку (проверьте, админ ли бот)", show_alert=True)
                return

            if can_complete:
                success, message = await db_complete_task_immediate(callback.from_user.id, task_id)
                
                if success:
                    msg_text = message
                    msg_text += f"\n\n⚠️ Не отписывайтесь {UNSUB_CHECK_DAYS} дней, иначе штраф x2!"
                    await callback.answer(msg_text, show_alert=True)
                    await show_earn_list(callback, state, bot, task_type, current_page)
                else:
                     await callback.answer(f"❌ {message}", show_alert=True)
            else:
                await callback.answer("❌ Вы не выполнили задание!", show_alert=True)

    # --- ОБРАБОТЧИК СКРИНШОТА ---
    @dp.message(AppStates.waiting_proof_screenshot, F.photo)
    async def process_screenshot_proof(message: types.Message, state: FSMContext):
        data = await state.get_data()
        task_id = data.get('current_task_id')
        
        if not task_id:
            await send_clean_message(message, state, bot, "❌ Ошибка контекста. Попробуйте снова выбрать задание.")
            await state.clear()
            return
            
        user_id = message.from_user.id
        
        # ИСПРАВЛЕНИЕ: используем database.db_pool
        async with database.db_pool.acquire() as conn:
            task_data = await conn.fetchrow("SELECT owner_id, task_type FROM tasks WHERE id=$1", task_id)
        
        if not task_data:
            await send_clean_message(message, state, bot, "❌ Задание не найдено.")
            await state.clear()
            return

        owner_id = task_data['owner_id']
        task_type_str = task_data['task_type'].upper()
        
        review_id = await db_create_review(user_id, task_id)
        if not review_id:
            await send_clean_message(message, state, bot, "❌ Ошибка сервера. Попробуйте позже.")
            await state.clear()
            return

        owner_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_approve_{review_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject_{review_id}")
            ]
        ])
        
        try:
            caption = (
                f"🛡️ <b>Проверьте выполнение вашего задания!</b>\n"
                f"Тип: <b>{task_type_str}</b>\n"
                f"Task ID: #{task_id}\n"
                f"Исполнитель: {message.from_user.full_name} (ID: {user_id})\n\n"
                f"Проверьте скриншот. Если все верно — подтвердите оплату."
            )
            await bot.send_photo(
                chat_id=owner_id,
                photo=message.photo[-1].file_id,
                caption=caption,
                reply_markup=owner_kb,
                parse_mode="HTML"
            )
            await send_clean_message(message, state, bot, "✅ <b>Скриншот отправлен заказчику!</b>\nОжидайте его подтверждения.", reply_markup=main_kb)
            
        except Exception as e:
            logger.error(f"Failed send to owner {owner_id}: {e}")
            await send_clean_message(message, state, bot, "❌ Не удалось отправить отчет заказчику (возможно, он заблокировал бота).", reply_markup=main_kb)
            
        await state.clear()

    @dp.callback_query(F.data.startswith("restore_"))
    async def process_restore_sub(callback: types.CallbackQuery, state: FSMContext):
        from database import db_refund_penalty
        task_id = int(callback.data.split("_")[1])
        
        # ИСПРАВЛЕНИЕ: используем database.db_pool
        async with database.db_pool.acquire() as conn:
            task = await conn.fetchrow(
                "SELECT channel_link, price_per_sub FROM tasks WHERE id=$1", 
                task_id
            )
        
        if not task:
            await callback.answer("❌ Задание не найдено", show_alert=True)
            return

        channel_username = task['channel_link'].replace('https://t.me/', '').replace('@', '').strip('/')
        
        try:
            member = await bot.get_chat_member(chat_id=f"@{channel_username}", user_id=callback.from_user.id)
            if member.status in ['member', 'administrator', 'creator']:
                refund_amount = float(task['price_per_sub']) * 2
                
                success, msg = await db_refund_penalty(callback.from_user.id, task_id, refund_amount)
                
                if success:
                    await safe_edit_message(
                        callback.message, state, bot,
                        f"✅ <b>Штраф аннулирован!</b>\n\n"
                        f"Вы подписались обратно на канал.\n"
                        f"💰 Возврат: +{int(refund_amount)} {CURRENCY_NAME}"
                    )
                else:
                    await callback.answer(f"❌ {msg}", show_alert=True)
            else:
                await callback.answer("❌ Вы все еще не подписаны на канал!", show_alert=True)
                
        except Exception as e:
            logger.error(f"Restore error: {e}")
            await callback.answer("❌ Ошибка проверки. Убедитесь, что бот админ в канале.", show_alert=True)