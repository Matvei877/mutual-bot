import asyncio
import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import database  # <--- Импортируем весь модуль, чтобы видеть обновления переменной
from database import db_apply_penalty
from config import UNSUB_CHECK_DAYS, CURRENCY_NAME

logger = logging.getLogger(__name__)

# --- ФОНОВАЯ ЗАДАЧА: МОНИТОРИНГ ОТПИСОК (5 ДНЕЙ) ---
async def monitor_unsubscribes(bot: Bot):
    """Проверяет подписки за последние 5 дней"""
    logger.info("🚀 Мониторинг отписок запущен")
    
    while True:
        try:
            # Ждем перед следующей проверкой
            await asyncio.sleep(60) 
            
            if database.db_pool is None:
                logger.warning("DB pool еще не инициализирован, ожидание...")
                await asyncio.sleep(10)
                continue
            
            # Запрос: берем только те записи, по которым еще не было штрафа
            query = f'''
                SELECT s.user_id, s.task_id, t.channel_link, t.channel_title, t.price_per_sub, t.task_type
                FROM subscriptions s
                JOIN tasks t ON s.task_id = t.id
                WHERE s.subscribed_at > NOW() - INTERVAL '{UNSUB_CHECK_DAYS} days'
                AND s.penalized = FALSE
                AND s.rewarded = TRUE
                AND t.task_type NOT IN ('view', 'reaction', 'bot')
            '''

            async with database.db_pool.acquire() as conn:
                recent_subs = await conn.fetch(query)
            
            if not recent_subs:
                continue

            for sub in recent_subs:
                user_id = sub['user_id']
                channel_link = sub['channel_link']
                task_id = sub['task_id']
                title = sub['channel_title'] or "Канал"
                
                # 1. Форматируем username для проверки
                # Убираем лишние символы из ссылки
                clean_target = channel_link.replace('https://t.me/', '').replace('@', '').split('?')[0].strip('/')
                
                # Если ссылка частная (содержит + или joinchat), get_chat_member не сработает по юзернейму
                if '+' in clean_target or 'joinchat' in clean_target:
                    logger.debug(f"Пропуск проверки для частной ссылки: {clean_target}")
                    continue

                is_member = False
                try:
                    # Пытаемся получить статус участника
                    member = await bot.get_chat_member(chat_id=f"@{clean_target}", user_id=user_id)
                    
                    if member.status in ['member', 'administrator', 'creator', 'restricted']:
                        is_member = True
                        
                except Exception as e:
                    # Если бот не админ в канале, Телеграм выдаст ошибку "Chat not found" или "Not enough rights"
                    logger.error(f"Ошибка проверки юзера {user_id} в {clean_target}: {e}")
                    # Важно: если мы не смогли проверить (например, бот не админ), 
                    # мы НЕ штрафуем, а просто идем дальше
                    continue 

                # 2. Если обнаружена отписка
                if not is_member:
                    penalty = float(sub['price_per_sub']) * 2
                    
                    # Списываем деньги в БД
                    success = await db_apply_penalty(user_id, task_id, penalty, title)
                    
                    if success:
                        logger.info(f"📉 Штраф применен к {user_id} за отписку от {title}")
                        
                        if not channel_link.startswith('http'):
                            valid_url = f"https://t.me/{channel_link.replace('@', '')}"
                        else:
                            valid_url = channel_link
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🔗 Подписаться обратно", url=valid_url)], # Используем валидный URL
                            [InlineKeyboardButton(text="🔄 Я подписался (Вернуть деньги)", callback_data=f"restore_{task_id}")]
                            ])
                        
                        try:
                            # Отправляем сообщение
                            await bot.send_message(
                                chat_id=user_id,
                                text=(
                                    f"🚨 <b>ОБНАРУЖЕНА ОТПИСКА!</b>\n\n"
                                    f"<b>Канал:</b> {title}\n"
                                    f"Вы нарушили правило обязательной подписки ({UNSUB_CHECK_DAYS} дней).\n\n"
                                    f"❌ <b>Списан штраф: -{int(penalty)} {CURRENCY_NAME}</b>\n\n"
                                    f"<i>Вернитесь в канал и нажмите кнопку ниже, чтобы вернуть средства.</i>"
                                ),
                                reply_markup=keyboard,
                                parse_mode="HTML"
                            )
                        except Exception as send_error:
                            logger.warning(f"Сообщение о штрафе не доставлено юзеру {user_id} (возможно бот в бане): {send_error}")

        except Exception as global_e:
            logger.error(f"Критическая ошибка в мониторинге: {global_e}")
            await asyncio.sleep(30) # Пауза перед рестартом при ошибке