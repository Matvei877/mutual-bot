import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_IDS = [1945280694, 1996797563] 

# КОНСТАНТЫ
CURRENCY_NAME = "FCOINS"
STARS_TO_FCOINS_RATE = 2000  
MIN_TASK_PRICE = 850.0      # Цена за подписку
MIN_VIEW_PRICE = 100.0      # Цена за просмотр
MIN_REACTION_PRICE = 150.0  # Цена за реакцию
MIN_BOT_PRICE = 800.0       # Цена за запуск бота
UNSUB_CHECK_DAYS = 5        # Срок обязательной подписки (дней)

if not TOKEN or not DATABASE_URL:
    raise ValueError("Не все переменные окружения установлены!")

