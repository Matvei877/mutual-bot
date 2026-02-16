import logging
import asyncio
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from keyboards import main_kb

logger = logging.getLogger(__name__)

# --- UI HELPERS ---

async def delete_old_messages(chat_id: int, state: FSMContext, bot: Bot):
    """
    Удаляет все сообщения бота, ID которых сохранены в состоянии.
    """
    data = await state.get_data()
    msg_ids = data.get('bot_msg_ids', [])
    if isinstance(msg_ids, int):
        msg_ids = [msg_ids]
    
    if not msg_ids:
        return

    for msg_id in msg_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
            
    # Очищаем список в состоянии, но не сохраняем пока

async def send_clean_message(message: Message, state: FSMContext, bot: Bot, text: str, reply_markup=None, parse_mode="HTML"):
    """
    1. Удаляет ВСЕ старые сообщения бота.
    2. Отправляет НОВОЕ сообщение.
    3. Сохраняет ID нового сообщения в список.
    """
    await delete_old_messages(message.chat.id, state, bot)

    if reply_markup is None:
        reply_markup = main_kb

    try:
        new_msg = await message.answer(
            text, 
            reply_markup=reply_markup, 
            parse_mode=parse_mode, 
            disable_web_page_preview=True
        )
        await state.update_data(bot_msg_ids=[new_msg.message_id])
        return new_msg
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None

async def restore_keyboard(chat_id: int, bot: Bot):
    """
    Восстанавливает reply keyboard, отправляя невидимое сообщение.
    Это гарантирует, что клавиатура всегда видна пользователю.
    Клавиатура остается видимой даже после удаления сообщения.
    """
    try:
        # Отправляем сообщение с клавиатурой
        keyboard_msg = await bot.send_message(
            chat_id=chat_id,
            text="\u200b",  # Невидимый символ (zero-width space)
            reply_markup=main_kb
        )
        # Небольшая задержка, чтобы Telegram успел показать клавиатуру
        await asyncio.sleep(0.2)
        # Удаляем сообщение, но клавиатура остается видимой благодаря is_persistent=True
        try:
            await bot.delete_message(chat_id=chat_id, message_id=keyboard_msg.message_id)
        except:
            pass
    except Exception as e:
        logger.debug(f"Could not restore keyboard: {e}")

async def safe_edit_message(message: Message, state: FSMContext, bot: Bot, text: str, reply_markup=None, parse_mode="HTML"):
    """
    Пытается отредактировать сообщение. 
    Если не получается — удаляет всё и шлет новое.
    После редактирования всегда восстанавливает reply keyboard.
    """
    try:
        await message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=True
        )
        await state.update_data(bot_msg_ids=[message.message_id])
        # Всегда восстанавливаем reply keyboard после редактирования inline-сообщения
        await restore_keyboard(message.chat.id, bot)
        return True
    except TelegramBadRequest:
        await send_clean_message(message, state, bot, text, reply_markup, parse_mode)
        return False
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        return False

