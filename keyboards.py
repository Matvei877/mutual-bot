from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)
from config import CURRENCY_NAME, STARS_TO_FCOINS_RATE

# --- KEYBOARDS ---
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💰 Заработать"), KeyboardButton(text="📢 Рекламировать")],
        [KeyboardButton(text="👤 Кабинет")],
        [KeyboardButton(text="📖 Инструкция"), KeyboardButton(text="📋 Условия")]
    ],
    resize_keyboard=True,
    is_persistent=True,
    one_time_keyboard=False,
    input_field_placeholder="Меню"
)

# --- HELPERS FOR KEYBOARDS ---
def get_deposit_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Купить FCOINS (Stars)", callback_data="topup_stars")],
        [InlineKeyboardButton(text="🔙 Вернуться", callback_data="back_to_start")]
    ])

def get_stars_amounts_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"50 ⭐ ({int(50 * STARS_TO_FCOINS_RATE)} {CURRENCY_NAME})", callback_data="stars_50")],
        [InlineKeyboardButton(text=f"100 ⭐ ({int(100 * STARS_TO_FCOINS_RATE)} {CURRENCY_NAME})", callback_data="stars_100")],
        [InlineKeyboardButton(text=f"200 ⭐ ({int(200 * STARS_TO_FCOINS_RATE)} {CURRENCY_NAME})", callback_data="stars_200")],
        [InlineKeyboardButton(text="✏️ Ввести своё кол-во", callback_data="stars_custom")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile_cb")]
    ])

def get_ads_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать задание", callback_data="ad_new")],
        [InlineKeyboardButton(text="📂 Мои задания", callback_data="ad_list")],
        [InlineKeyboardButton(text="🔙 Вернуться", callback_data="back_to_start")]
    ])

def get_create_task_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Канал", callback_data="type_channel"), InlineKeyboardButton(text="👥 Группа", callback_data="type_group")],
        [InlineKeyboardButton(text="🤖 Бот", callback_data="type_bot")],
        [InlineKeyboardButton(text="👁️ Просмотры", callback_data="type_view"), InlineKeyboardButton(text="❤️ Реакции", callback_data="type_reaction")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="ad_menu")]
    ])

def get_earn_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", callback_data="earn_channel")],
        [InlineKeyboardButton(text="👥 Вступить в группу", callback_data="earn_group")],
        [InlineKeyboardButton(text="🤖 Запустить бота", callback_data="earn_bot")],
        [InlineKeyboardButton(text="👁️ Смотреть посты", callback_data="earn_view")],
        [InlineKeyboardButton(text="❤️ Ставить реакции", callback_data="earn_reaction")],
        [InlineKeyboardButton(text="🔙 Вернуться", callback_data="back_to_start")]
    ])

def get_back_to_earn_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_earn_menu")]
    ])

def get_back_to_ads_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ad_menu")]
    ])

def get_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_paginated_kb(tasks, page, total_count, per_page, mode="earn", task_type="channel"):
    builder = InlineKeyboardMarkup(inline_keyboard=[])
    rows = []

    for task in tasks:
        if mode == "earn":
            link = task['channel_link']
            
            # Приводим любые ссылки (@username или просто username) к формату https://t.me/username
            if not link.startswith('http'):
                link = f"https://t.me/{link.lstrip('@')}"

            price = float(task['price_per_sub'])
            title = task['channel_title']
            if not title: title = "Task"
            if len(title) > 15: title = title[:15] + "..."
            
            icon = "📢"
            btn_text = "✅ Проверить"
            
            if task_type == 'view':
                icon = "👁️"
                btn_text = "💰 Получить награду"
            elif task_type == 'reaction':
                icon = "❤️"
                btn_text = "💰 Получить награду"
            elif task_type == 'bot':
                icon = "🤖"
                btn_text = "💰 Получить награду"
            elif task_type == 'group':
                icon = "👥"

            rows.append([
                InlineKeyboardButton(
                    # ИЗМЕНЕНО ЗДЕСЬ: Сначала цена, потом название
                    text=f"{icon} {price:.0f} {CURRENCY_NAME} | {title}",
                    url=link 
                ),
                InlineKeyboardButton(
                    text=btn_text, 
                    callback_data=f"check_{task['id']}_{page}_{task_type}"
                )
            ])
        
        elif mode == "myads": 
            status = "🟢" if task['active'] and task['count_done'] < task['count_needed'] else "🔴"
            title = task['channel_title']
            
            icon = "📢"
            if task['task_type'] == 'group': icon = "👥"
            elif task['task_type'] == 'view': icon = "👁️"
            elif task['task_type'] == 'reaction': icon = "❤️"
            elif task['task_type'] == 'bot': icon = "🤖"
            
            if not title: title = "Задание"
            
            rows.append([
                InlineKeyboardButton(
                    text=f"{status} {icon} {title} | {task['count_done']}/{task['count_needed']}",
                    callback_data="ignore"
                )
            ])

    builder.inline_keyboard = rows

    total_pages = (total_count + per_page - 1) // per_page
    if total_pages > 1:
        pagination_row = []
        key = f"{mode}"
        if mode == "earn": key += f"_{task_type}"

        if page > 1:
            pagination_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"page_{key}_{page-1}"))
        else:
            pagination_row.append(InlineKeyboardButton(text="⏺️", callback_data="ignore"))
        
        pagination_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore"))
        
        if page < total_pages:
            pagination_row.append(InlineKeyboardButton(text="➡️", callback_data=f"page_{key}_{page+1}"))
        else:
            pagination_row.append(InlineKeyboardButton(text="⏺️", callback_data="ignore"))
            
        builder.inline_keyboard.append(pagination_row)

    if mode == "earn":
        builder.inline_keyboard.append([InlineKeyboardButton(text="🔴 Пожаловаться", callback_data="report")])
        builder.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_earn_menu")])
        
    elif mode == "myads":
        builder.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="ad_menu")])
    else:
        builder.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu_return")])

    return builder