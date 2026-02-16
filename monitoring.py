import asyncio
import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_pool, db_apply_penalty
from config import UNSUB_CHECK_DAYS, CURRENCY_NAME

logger = logging.getLogger(__name__)

# --- ФОНОВАЯ ЗАДАЧА: МОНИТОРИНГ ОТПИСОК (5 ДНЕЙ) ---
async def monitor_unsubscribes(bot: Bot):
    """Проверяет подписки за последние 5 дней"""
    logger.info("🚀 Мониторинг отписок запущен")
    while True:
        try:
            await asyncio.sleep(25) 
            
            # Проверяем, что пул БД инициализирован
            if db_pool is None:
                logger.warning("DB pool not initialized yet, waiting...")
                await asyncio.sleep(10)
                continue
            
            query = f'''
                    SELECT s.user_id, s.task_id, t.channel_link, t.channel_title, t.price_per_sub, t.task_type
                    FROM subscriptions s
                    JOIN tasks t ON s.task_id = t.id
                    WHERE s.subscribed_at > NOW() - INTERVAL '{UNSUB_CHECK_DAYS} days'
                    AND s.penalized = FALSE
                    AND s.rewarded = TRUE
                    AND t.task_type NOT IN ('view', 'reaction', 'bot')
                '''

            async with db_pool.acquire() as conn:
                recent_subs = await conn.fetch(query)
            
            for sub in recent_subs:
                user_id = sub['user_id']
                channel_link = sub['channel_link']
                task_id = sub['task_id']
                
                channel_username = channel_link.replace('https://t.me/', '').replace('@', '').strip('/')
                if not channel_username: continue
                
                is_member = False
                try:
                    member = await bot.get_chat_member(chat_id=f"@{channel_username}", user_id=user_id)
                    if member.status in ['member', 'administrator', 'creator', 'restricted']:
                        is_member = True
                except Exception:
                    continue 

                if not is_member:
                    penalty = float(sub['price_per_sub']) * 2
                    title = sub['channel_title'] or "Channel"
                    
                    success = await db_apply_penalty(user_id, task_id, penalty, title)
                    
                    if success:
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🔗 Подписаться обратно", url=channel_link)],
                            [InlineKeyboardButton(text="🔄 Я подписался (Вернуть деньги)", callback_data=f"restore_{task_id}")]
                        ])
                        
                        try:
                            await bot.send_message(
                                user_id,
                                f"🚨 <b>ОБНАРУЖЕНА ОТПИСКА!</b>\n\n"
                                f"Канал: {title}\n"
                                f"Вы нарушили правило {UNSUB_CHECK_DAYS} дней.\n"
                                f"❌ <b>Штраф: -{int(penalty)} {CURRENCY_NAME}</b>\n\n"
                                f"👇 Если это ошибка или вы подписались обратно, нажмите кнопку ниже:",
                                reply_markup=keyboard,
                                parse_mode="HTML"
                            )
                        except: pass

        except Exception as e:
            logger.error(f"Global monitor error: {e}")
            await asyncio.sleep(60)

