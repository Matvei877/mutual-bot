import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import TOKEN
import database # <--- Импортируем модуль целиком
from database import init_db
from monitoring import monitor_unsubscribes

# Импортируем все обработчики
from handlers.main_menu import register_main_menu_handlers
from handlers.common import register_common_handlers
from handlers.payment import register_payment_handlers
from handlers.earn import register_earn_handlers
from handlers.advertise import register_advertise_handlers
from handlers.admin import register_admin_handlers

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Регистрируем все обработчики
register_main_menu_handlers(dp, bot)
register_common_handlers(dp, bot)
register_payment_handlers(dp, bot)
register_earn_handlers(dp, bot)
register_advertise_handlers(dp, bot)
register_admin_handlers(dp, bot)

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем фоновый мониторинг отписок
    asyncio.create_task(monitor_unsubscribes(bot))
    
    try:
        logger.info("Bot started (Persistent Menu Mode)")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        # ВАЖНО: Используем database.db_pool для проверки и закрытия
        if database.db_pool: 
            await database.db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())