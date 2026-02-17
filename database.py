import asyncpg
import logging
from config import DATABASE_URL, CURRENCY_NAME, UNSUB_CHECK_DAYS

logger = logging.getLogger(__name__)

db_pool = None

# --- БАЗА ДАННЫХ ---
async def init_db():
    global db_pool
    
    db_pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=2, max_size=10)
    logger.info("Пул БД создан")
    
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                balance NUMERIC(10, 4) DEFAULT 0.0,
                earned_balance NUMERIC(10, 4) DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT NOW()
            );
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_id TEXT PRIMARY KEY, 
                user_id BIGINT,
                amount NUMERIC(10, 4),
                payment_type TEXT DEFAULT 'stars',
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW()
            );
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                owner_id BIGINT,
                channel_link TEXT,
                channel_title TEXT, 
                task_type TEXT DEFAULT 'channel',
                price_per_sub NUMERIC(10, 4), 
                count_needed INTEGER,
                count_done INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS completed (
                user_id BIGINT,
                task_id INTEGER,
                completed_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (user_id, task_id)
            );
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id BIGINT,
                task_id INTEGER,
                subscribed_at TIMESTAMP DEFAULT NOW(),
                checked_at TIMESTAMP,
                rewarded BOOLEAN DEFAULT TRUE,
                penalized BOOLEAN DEFAULT FALSE, 
                PRIMARY KEY (user_id, task_id)
            );
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount NUMERIC(10, 4),
                type TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS pending_reviews (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                task_id INTEGER,
                status TEXT DEFAULT 'pending', 
                created_at TIMESTAMP DEFAULT NOW()
            );
        ''')
        
        logger.info("✅ Таблицы БД созданы/проверены")

# --- DB HELPERS ---
async def db_get_user(user_id):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", 
                user_id
            )
            row = await conn.fetchrow("SELECT balance, earned_balance FROM users WHERE user_id = $1", user_id)
            if row:
                return float(row['balance']), float(row['earned_balance'])
            return 0.0, 0.0
    except Exception as e:
        logger.error(f"Ошибка получения пользователя {user_id}: {e}")
        return 0.0, 0.0

async def db_update_balance(user_id, amount, tx_type=None, description=None, is_earned=False, force=False):
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow(
                    "SELECT balance, earned_balance FROM users WHERE user_id = $1 FOR UPDATE", 
                    user_id
                )
                
                if current is None:
                    await conn.execute("INSERT INTO users (user_id) VALUES ($1)", user_id)
                    current = {'balance': 0.0, 'earned_balance': 0.0}
                
                if amount < 0 and not force:
                    if is_earned:
                        if float(current['earned_balance']) < abs(amount):
                            raise ValueError("Недостаточно заработанных средств")
                    else:
                        if float(current['balance']) < abs(amount):
                            raise ValueError("Недостаточно средств")
                
                if is_earned:
                    await conn.execute(
                        "UPDATE users SET earned_balance = earned_balance + $1 WHERE user_id = $2", 
                        float(amount), user_id
                    )
                else:
                    await conn.execute(
                        "UPDATE users SET balance = balance + $1 WHERE user_id = $2", 
                        float(amount), user_id
                    )
                
                if tx_type:
                    await conn.execute(
                        "INSERT INTO transactions (user_id, amount, type, description) VALUES ($1, $2, $3, $4)",
                        user_id, float(amount), tx_type, description
                    )
                return True
                
    except Exception as e:
        logger.error(f"Ошибка обновления баланса {user_id}: {e}")
        raise

async def db_get_global_stats():
    try:
        async with db_pool.acquire() as conn:
            users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
            tasks_today = await conn.fetchval("SELECT COUNT(*) FROM completed WHERE completed_at >= CURRENT_DATE")
            return int(users_count), int(tasks_today)
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return 0, 0

async def db_add_task(owner_id, link, title, task_type, price, count):
    try:
        async with db_pool.acquire() as conn:
            task_id = await conn.fetchval(
                "INSERT INTO tasks (owner_id, channel_link, channel_title, task_type, price_per_sub, count_needed) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                owner_id, link, title, task_type, float(price), int(count)
            )
            return task_id
    except Exception as e:
        logger.error(f"Ошибка создания задания: {e}")
        raise

async def db_refund_penalty(user_id, task_id, refund_amount):
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                is_penalized = await conn.fetchval(
                    "SELECT penalized FROM subscriptions WHERE user_id=$1 AND task_id=$2",
                    user_id, task_id
                )
                
                if not is_penalized:
                    return False, "Штраф уже снят или не был наложен."

                await conn.execute(
                    "UPDATE users SET earned_balance = earned_balance + $1 WHERE user_id = $2", 
                    float(refund_amount), user_id
                )
                await conn.execute(
                    "UPDATE subscriptions SET penalized = FALSE WHERE user_id = $1 AND task_id = $2",
                    user_id, task_id
                )
                await conn.execute(
                    "INSERT INTO transactions (user_id, amount, type, description) VALUES ($1, $2, 'refund_penalty', $3)",
                    user_id, float(refund_amount), f'Возврат штрафа за задачу #{task_id}'
                )
                return True, "Штраф успешно снят!"
    except Exception as e:
        logger.error(f"Ошибка возврата штрафа: {e}")
        return False, "Ошибка базы данных"
    
async def db_get_tasks_paginated(user_id, task_type, page=1, per_page=5):
    offset = (page - 1) * per_page
    try:
        async with db_pool.acquire() as conn:
            total_count = await conn.fetchval('''
                SELECT COUNT(*) FROM tasks 
                WHERE active = TRUE 
                AND task_type = $2
                AND count_done < count_needed 
                AND owner_id != $1
                AND id NOT IN (SELECT task_id FROM completed WHERE user_id = $1)
            ''', user_id, task_type)

            tasks = await conn.fetch('''
                SELECT id, channel_link, channel_title, price_per_sub, task_type
                FROM tasks 
                WHERE active = TRUE 
                AND task_type = $2
                AND count_done < count_needed 
                AND owner_id != $1
                AND id NOT IN (SELECT task_id FROM completed WHERE user_id = $1)
                ORDER BY price_per_sub DESC, created_at DESC
                LIMIT $3 OFFSET $4
            ''', user_id, task_type, per_page, offset)
            
            return tasks, total_count
    except Exception as e:
        logger.error(f"Ошибка пагинации: {e}")
        return [], 0

async def db_get_available_counts(user_id):
    try:
        async with db_pool.acquire() as conn:
            base_condition = '''
                active = TRUE 
                AND count_done < count_needed 
                AND owner_id != $1
                AND id NOT IN (SELECT task_id FROM completed WHERE user_id = $1)
            '''
            
            channels = await conn.fetchval(f"SELECT COUNT(*) FROM tasks WHERE task_type = 'channel' AND {base_condition}", user_id)
            groups = await conn.fetchval(f"SELECT COUNT(*) FROM tasks WHERE task_type = 'group' AND {base_condition}", user_id)
            views = await conn.fetchval(f"SELECT COUNT(*) FROM tasks WHERE task_type = 'view' AND {base_condition}", user_id)
            reactions = await conn.fetchval(f"SELECT COUNT(*) FROM tasks WHERE task_type = 'reaction' AND {base_condition}", user_id)
            bots = await conn.fetchval(f"SELECT COUNT(*) FROM tasks WHERE task_type = 'bot' AND {base_condition}", user_id)
            
            return int(channels), int(groups), int(views), int(reactions), int(bots)
    except Exception as e:
        logger.error(f"Ошибка подсчета заданий: {e}")
        return 0, 0, 0, 0, 0

async def db_get_my_tasks_paginated(user_id, page=1, per_page=5):
    offset = (page - 1) * per_page
    try:
        async with db_pool.acquire() as conn:
            total_count = await conn.fetchval('SELECT COUNT(*) FROM tasks WHERE owner_id = $1', user_id)
            
            tasks = await conn.fetch('''
                SELECT id, channel_link, channel_title, task_type, price_per_sub, count_needed, count_done, active 
                FROM tasks WHERE owner_id = $1 
                ORDER BY created_at DESC 
                LIMIT $2 OFFSET $3
            ''', user_id, per_page, offset)
            
            return tasks, total_count
    except Exception:
        return [], 0

# --- МГНОВЕННОЕ ВЫПОЛНЕНИЕ ---
async def db_complete_task_immediate(user_id, task_id):
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                exists = await conn.fetchval("SELECT 1 FROM completed WHERE user_id=$1 AND task_id=$2", user_id, task_id)
                if exists: 
                    return False, "Задание уже выполнено"
                
                task = await conn.fetchrow(
                    "SELECT count_done, count_needed, active, price_per_sub, task_type FROM tasks WHERE id = $1 FOR UPDATE",
                    task_id
                )
                if not task or not task['active'] or task['count_done'] >= task['count_needed']:
                    return False, "Задание неактивно или лимит исчерпан"
                
                actual_price = float(task['price_per_sub'])
                task_type = task['task_type']
                
                # 1. Добавляем в completed
                await conn.execute("INSERT INTO completed (user_id, task_id) VALUES ($1, $2)", user_id, task_id)
                
                # 2. МОНИТОРИНГ
                if task_type not in ['view', 'reaction', 'bot']:
                    await conn.execute(
                        """INSERT INTO subscriptions (user_id, task_id, subscribed_at, rewarded) 
                           VALUES ($1, $2, NOW(), TRUE) 
                           ON CONFLICT (user_id, task_id) DO UPDATE SET subscribed_at = NOW(), rewarded = TRUE""",
                        user_id, task_id
                    )
                
                # 3. Обновляем счетчик задания
                await conn.execute("UPDATE tasks SET count_done = count_done + 1 WHERE id = $1", task_id)
                
                # 4. Начисляем баланс
                await conn.execute(
                    "UPDATE users SET earned_balance = earned_balance + $1 WHERE user_id = $2", 
                    actual_price, user_id
                )
                
                # 5. Пишем транзакцию
                await conn.execute(
                    "INSERT INTO transactions (user_id, amount, type, description) VALUES ($1, $2, $3, $4)",
                    user_id, actual_price, 'task_earn', f'Выполнение задания #{task_id} ({task_type})'
                )
                
                return True, f"✅ Получено {int(actual_price)} {CURRENCY_NAME}"
                
    except Exception as e:
        logger.error(f"Ошибка завершения задания: {e}")
        return False, "Ошибка обработки"

async def db_apply_penalty(user_id, task_id, penalty_amount, channel_title):
    try:
        # 1. Списываем баланс
        await db_update_balance(
            user_id, 
            -float(penalty_amount), 
            tx_type='penalty', 
            description=f'Штраф за отписку: {channel_title}', 
            is_earned=True, 
            force=True
        )
        # 2. ОЧЕНЬ ВАЖНО: Ставим флаг, что штраф уже наложен
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE subscriptions SET penalized = TRUE WHERE user_id = $1 AND task_id = $2",
                user_id, task_id
            )
        return True
    except Exception as e:
        logger.error(f"Ошибка применения штрафа: {e}")
        return False

async def db_add_invoice(invoice_id, user_id, amount):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO invoices (invoice_id, user_id, amount, payment_type) VALUES ($1, $2, $3, 'stars')", 
                str(invoice_id), user_id, float(amount)
            )
    except Exception as e:
        logger.error(f"Ошибка инвойса: {e}")

# --- DB HELPERS FOR REVIEWS ---
async def db_create_review(user_id, task_id):
    try:
        async with db_pool.acquire() as conn:
            review_id = await conn.fetchval(
                "INSERT INTO pending_reviews (user_id, task_id) VALUES ($1, $2) RETURNING id",
                user_id, task_id
            )
            return review_id
    except Exception as e:
        logger.error(f"Error creating review: {e}")
        return None

async def db_get_review(review_id):
    try:
        async with db_pool.acquire() as conn:
            return await conn.fetchrow("SELECT user_id, task_id FROM pending_reviews WHERE id=$1", int(review_id))
    except Exception:
        return None

async def db_delete_review(review_id):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM pending_reviews WHERE id=$1", int(review_id))
    except Exception:
        pass

