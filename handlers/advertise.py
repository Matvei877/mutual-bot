import re
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from database import (
    db_get_user, db_add_task, db_update_balance, db_get_my_tasks_paginated, db_pool
)
from keyboards import (
    get_ads_menu_kb, get_create_task_type_kb, get_cancel_kb, 
    get_back_to_ads_kb, get_paginated_kb, main_kb
)
from states import AppStates
from utils import send_clean_message, safe_edit_message
from config import (
    MIN_TASK_PRICE, MIN_VIEW_PRICE, MIN_REACTION_PRICE, MIN_BOT_PRICE, CURRENCY_NAME
)

logger = logging.getLogger(__name__)

async def show_my_ads_page(callback, state: FSMContext, bot: Bot, page=1):
    per_page = 5
    tasks, total_count = await db_get_my_tasks_paginated(callback.from_user.id, page, per_page)
    
    if total_count == 0:
        await safe_edit_message(
            callback.message, state, bot,
            "📭 У вас нет активных заданий",
            reply_markup=get_back_to_ads_kb()
        )
        return

    text = "📂 <b>Ваши задания:</b>\n🟢 Активно | 🔴 Остановлено"
    kb = get_paginated_kb(tasks, page, total_count, per_page, mode="myads")
    await safe_edit_message(callback.message, state, bot, text, reply_markup=kb)

def register_advertise_handlers(dp: Dispatcher, bot: Bot):
    # --- АВТОМАТИЧЕСКОЕ ДОБАВЛЕНИЕ КАНАЛА ---
    @dp.my_chat_member()
    async def on_bot_channel_status_changed(event: ChatMemberUpdated, state: FSMContext):
        new_status = event.new_chat_member.status
        if new_status != "administrator":
            return

        chat = event.chat
        user = event.from_user

        if chat.type == "channel":
            ad_type = "channel"
            type_text = "📢 Канал"
        elif chat.type in ["group", "supergroup"]:
            ad_type = "group"
            type_text = "👥 Группа"
        else:
            return

        link = None
        if chat.username:
            link = f"@{chat.username}"
        else:
            try:
                invite = await bot.create_chat_invite_link(chat.id, name="Mutual Bot")
                link = invite.invite_link
            except Exception as e:
                logger.error(f"Не удалось создать ссылку для чата {chat.id}: {e}")

        if not link:
            return 

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Создать задание", callback_data=f"fast_setup_{chat.id}_{ad_type}")],
            [InlineKeyboardButton(text="🔙 Вернуться", callback_data="back_to_start")]
        ])

        try:
            await bot.send_message(
                chat_id=user.id,
                text=f"✅ <b>Бот успешно подключен!</b>\n\n"
                     f"{type_text}: <b>{chat.title}</b>\n"
                     f"🔗 Ссылка: {link}\n\n"
                     f"Хотите сразу создать задание на накрутку?",
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception:
            pass

    @dp.callback_query(F.data.startswith("fast_setup_"))
    async def process_fast_setup(callback: types.CallbackQuery, state: FSMContext):
        parts = callback.data.split("_")
        chat_id = int(parts[2])
        ad_type = parts[3]

        try:
            chat = await bot.get_chat(chat_id)
            
            link = f"@{chat.username}" if chat.username else None
            if not link:
                try:
                    invite_link = await bot.create_chat_invite_link(chat.id)
                    link = invite_link.invite_link
                except:
                    pass

            if not link:
                await callback.answer("❌ Ошибка получения ссылки. Попробуйте вручную.", show_alert=True)
                return

            await state.update_data(
                ad_type=ad_type,
                link=link,
                target_chat_id=chat_id 
            )

            text_type = 'подписчиков' if ad_type == 'channel' else 'вступлений'
            
            await safe_edit_message(
                callback.message, state, bot,
                f"🚀 Настройка задания для <b>{chat.title}</b>\n\n"
                f"📊 Сколько {text_type} нужно?",
                reply_markup=get_cancel_kb()
            )
            
            await state.set_state(AppStates.waiting_ad_count)
            
        except Exception as e:
            await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

    # --- РЕКЛАМА ---
    @dp.callback_query(F.data == "ad_new")
    async def cb_new_ad(callback: types.CallbackQuery, state: FSMContext):
        await safe_edit_message(
            callback.message, state, bot,
            "➕ <b>Выберите тип задания:</b>",
            reply_markup=get_create_task_type_kb()
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("type_"))
    async def cb_select_type(callback: types.CallbackQuery, state: FSMContext):
        selected_type = callback.data.split("_")[1] # channel, group, view, reaction, bot
        
        await state.update_data(ad_type=selected_type)
        
        bot_info = await bot.get_me()
        bot_username = bot_info.username

        kb_rows = []
        
        if selected_type == 'view':
            msg = "👁️ <b>Реклама поста (Просмотры)</b>\n\nОтправьте ссылку на пост\n(например: <code>https://t.me/durov/123</code>)\n\n<b>ИЛИ просто перешлите сообщение из канала сюда.</b>"
        elif selected_type == 'reaction':
            msg = "❤️ <b>Накрутка реакций</b>\n\nОтправьте ссылку на пост, где нужны реакции\n(например: <code>https://t.me/durov/123</code>)"
        elif selected_type == 'bot':
            msg = (
                "🤖 <b>Реклама бота</b>\n\n"
                "Отправьте ссылку на бота (например: <code>@BotName</code> или <code>https://t.me/BotName</code>).\n\n"
                "⚠️ Пользователи должны будут запустить бота и прислать скриншот."
            )
        elif selected_type == 'group':
            msg = (
                "👥 <b>Реклама группы</b>\n\n"
                "Вы можете отправить ссылку (@group) вручную.\n"
                "<b>ИЛИ</b> нажмите кнопку ниже, чтобы выбрать группу и добавить туда бота автоматически."
            )
            add_url = f"https://t.me/{bot_username}?startgroup&admin=invite_users+change_info"
            kb_rows.append([InlineKeyboardButton(text="➕ Добавить бота в группу", url=add_url)])
            
        else: # channel
            msg = (
                "📢 <b>Реклама канала</b>\n\n"
                "Вы можете отправить ссылку (@channel) вручную.\n"
                "<b>ИЛИ</b> нажмите кнопку ниже, чтобы выбрать канал и добавить туда бота автоматически."
            )
            add_url = f"https://t.me/{bot_username}?startchannel&admin=post_messages+edit_messages+invite_users"
            kb_rows.append([InlineKeyboardButton(text="➕ Добавить бота в канал", url=add_url)])
        
        if selected_type not in ['bot', 'view', 'reaction']:
            msg += "\n\n⚠️ Бот должен быть администратором!"
        
        kb_rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
        kb_rows.append([InlineKeyboardButton(text="🔙 Вернуться", callback_data="back_to_start")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        
        await safe_edit_message(callback.message, state, bot, msg, reply_markup=keyboard)
        await state.set_state(AppStates.waiting_ad_link)
        await callback.answer()

    @dp.callback_query(F.data == "ad_list")
    async def cb_my_ads(callback: types.CallbackQuery, state: FSMContext):
        await show_my_ads_page(callback, state, bot, page=1)
        await callback.answer()

    @dp.callback_query(F.data == "ad_menu")
    async def cb_back_to_ads_menu(callback: types.CallbackQuery, state: FSMContext):
        await safe_edit_message(
            callback.message, state, bot,
            "📢 <b>Раздел рекламы</b>",
            reply_markup=get_ads_menu_kb()
        )
        await callback.answer()

    @dp.message(AppStates.waiting_ad_link)
    async def process_ad_link(message: types.Message, state: FSMContext):
        data = await state.get_data()
        ad_type = data.get('ad_type', 'channel') 
        
        link = None

        if message.forward_from_chat:
            chat = message.forward_from_chat
            if chat.type == 'channel' and chat.username:
                if ad_type in ['view', 'reaction']:
                    link = f"https://t.me/{chat.username}/{message.forward_from_message_id}"
                else:
                    link = f"@{chat.username}"
            else:
                await send_clean_message(message, state, bot, "❌ Не удалось определить ссылку.\nУбедитесь, что канал публичный (имеет @ссылку), и попробуйте отправить ссылку вручную.")
                return

        elif message.text:
            link = message.text.strip()
        
        if not link:
            await send_clean_message(message, state, bot, "❌ Пожалуйста, отправьте ссылку или перешлите сообщение.")
            return

        if ad_type in ['view', 'reaction']:
            if not re.search(r"t\.me/.+/\d+$", link):
                 await send_clean_message(message, state, bot, "❌ Это не ссылка на пост.\nПример: https://t.me/channel/123\nИли просто перешлите пост из канала.")
                 return
        elif ad_type == 'bot':
            if 't.me/' not in link and not link.startswith('@'):
                 await send_clean_message(message, state, bot, "❌ Некорректная ссылка на бота (нужен @botname или https://t.me/botname).")
                 return
            if '/p/' in link or re.search(r"/\d+$", link):
                 await send_clean_message(message, state, bot, "❌ Вы выбрали 'Бот', но кидаете ссылку на пост.")
                 return
        else:
            if not link.startswith('@') and 'https://t.me/' not in link:
                 await send_clean_message(message, state, bot, "❌ Некорректная ссылка (нужен @username или https://t.me/...)")
                 return
            if re.search(r"t\.me/.+/\d+$", link):
                 await send_clean_message(message, state, bot, "❌ Вы выбрали рекламу Канала/Группы, а кидаете ссылку на пост.\nПожалуйста, отправьте ссылку на сам канал.")
                 return

        await state.update_data(link=link)
        
        text_type_map = {
            'view': 'просмотров', 
            'reaction': 'реакций', 
            'channel': 'подписчиков', 
            'group': 'вступлений',
            'bot': 'запусков'
        }
        text_type = text_type_map.get(ad_type, 'подписчиков')
        
        await send_clean_message(message, state, bot, f"📊 Сколько {text_type} нужно?", reply_markup=get_cancel_kb())
        await state.set_state(AppStates.waiting_ad_count)

    @dp.message(AppStates.waiting_ad_count)
    async def process_ad_count(message: types.Message, state: FSMContext):
        if not message.text.isdigit():
            await send_clean_message(message, state, bot, "❌ Введите число")
            return
        count = int(message.text)
        if count <= 0: return
        
        await state.update_data(count=count)
        
        data = await state.get_data()
        ad_type = data.get('ad_type', 'channel')
        
        min_price = MIN_TASK_PRICE
        if ad_type == 'view':
            min_price = MIN_VIEW_PRICE
        elif ad_type == 'reaction':
            min_price = MIN_REACTION_PRICE
        elif ad_type == 'bot':
            min_price = MIN_BOT_PRICE
        
        type_name_map = {
            'view': 'просмотр', 
            'reaction': 'реакцию',
            'channel': 'подписчика', 
            'group': 'подписчика',
            'bot': 'запуск'
        }
        type_name = type_name_map.get(ad_type, 'подписчика')
        
        await send_clean_message(
            message, state, bot,
            f"💰 Цена за 1 {type_name} в {CURRENCY_NAME}\n"
            f"Минимально: {int(min_price)} {CURRENCY_NAME}",
            reply_markup=get_cancel_kb()
        )
        await state.set_state(AppStates.waiting_ad_price)

    @dp.message(AppStates.waiting_ad_price)
    async def process_ad_price(message: types.Message, state: FSMContext):
        try:
            data = await state.get_data()
            ad_type = data.get('ad_type', 'channel')
            link = data['link']
            target_chat_id = data.get('target_chat_id') 
            
            min_price = MIN_TASK_PRICE
            if ad_type == 'view':
                min_price = MIN_VIEW_PRICE
            elif ad_type == 'reaction':
                min_price = MIN_REACTION_PRICE
            elif ad_type == 'bot':
                min_price = MIN_BOT_PRICE
            
            price = float(message.text)
            if price < min_price:
                await send_clean_message(message, state, bot, f"❌ Минимум {int(min_price)} {CURRENCY_NAME}")
                return
            
            chat_identifier = None
            channel_title = "Unknown"

            # Предварительная подготовка данных (парсинг)
            if ad_type == 'bot':
                 channel_title = link.replace('https://t.me/', '').replace('@', '')
                 if not channel_title.startswith('@'): channel_title = f"@{channel_title}"
            elif ad_type in ['view', 'reaction']:
                match = re.search(r"t\.me/([^/]+)/\d+", link)
                if match:
                    chat_identifier = f"@{match.group(1)}"
                else:
                    await send_clean_message(message, state, bot, "❌ Ошибка парсинга ссылки на пост")
                    return
            else:
                if target_chat_id:
                    chat_identifier = target_chat_id
                else:
                    clean_link = link.replace('https://t.me/', '').replace('joinchat/', '').replace('+', '')
                    if clean_link.startswith('@'):
                        chat_identifier = clean_link
                    elif link.startswith('https://t.me/+') or 'joinchat' in link:
                        await send_clean_message(message, state, bot, "❌ При ручном вводе инвайт-ссылки бот не может проверить права.\nПожалуйста, используйте @username публичного канала ИЛИ добавьте бота в админы через кнопку в меню.")
                        return
                    else:
                        if not clean_link.startswith('-'): 
                             chat_identifier = f"@{clean_link}"
                        else:
                             chat_identifier = clean_link
            
            # Проверки прав (кроме ботов)
            if ad_type != 'bot':
                try:
                    chat = await bot.get_chat(chat_identifier)
                    channel_title = chat.title
                    
                    if ad_type == 'group':
                        if chat.type not in ['group', 'supergroup']:
                            await send_clean_message(message, state, bot, "❌ Вы выбрали 'Группа', но это канал.")
                            return
                    elif ad_type == 'channel':
                        if chat.type != 'channel':
                            await send_clean_message(message, state, bot, "❌ Вы выбрали 'Канал', но это группа.")
                            return
                    
                    member = await bot.get_chat_member(chat.id, bot.id)
                    if member.status != 'administrator':
                        raise ValueError("Bot not admin")
                        
                except ValueError:
                    await send_clean_message(message, state, bot, 
                        f"❌ <b>Бот не администратор!</b>\n"
                        f"Добавьте бота в администраторы канала/группы и попробуйте снова.",
                        reply_markup=get_cancel_kb()
                    )
                    return
                except Exception as e:
                    logger.error(f"Ad check failed: {e}")
                    await send_clean_message(message, state, bot, f"❌ Не удалось получить доступ к чату. Ошибка: {e}")
                    return 

            cost = price * data['count']
            balance, earned = await db_get_user(message.from_user.id)
            total = balance + earned
            
            if total < cost:
                await send_clean_message(message, state, bot, f"❌ Не хватает средств. Нужно: {int(cost)} {CURRENCY_NAME}, у вас: {int(total)} {CURRENCY_NAME}")
                await state.clear()
                return
            
            if balance >= cost:
                await db_update_balance(message.from_user.id, -cost, 'task_create', f'Задание {data["count"]} ({ad_type})', False)
            else:
                if balance > 0:
                    await db_update_balance(message.from_user.id, -balance, 'task_create', 'Часть оплаты 1', False)
                remaining = cost - balance
                await db_update_balance(message.from_user.id, -remaining, 'task_create', 'Часть оплаты 2', True)
            
            task_id = await db_add_task(message.from_user.id, data['link'], channel_title, ad_type, price, data['count'])

            type_icon_map = {'view': '👁️', 'reaction': '❤️', 'channel': '📢', 'group': '👥', 'bot': '🤖'}
            icon = type_icon_map.get(ad_type, '📢')
            
            await send_clean_message(
                message, state, bot,
                f"✅ Задание #{task_id} создано!\n"
                f"{icon} <b>{channel_title}</b>\n"
                f"Списано: {int(cost)} {CURRENCY_NAME}",
                reply_markup=main_kb
            )
            await state.clear()
        except ValueError:
            await send_clean_message(message, state, bot, "❌ Введите число")

