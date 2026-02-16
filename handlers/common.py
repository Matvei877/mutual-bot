from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from utils import delete_old_messages, send_clean_message, restore_keyboard
from keyboards import main_kb
from handlers.earn import show_earn_list
from handlers.advertise import show_my_ads_page

def register_common_handlers(dp: Dispatcher, bot: Bot):
    @dp.callback_query(F.data == "cancel")
    async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
        await delete_old_messages(callback.message.chat.id, state, bot)
        await state.clear()
        await send_clean_message(callback.message, state, bot, "Главное меню", reply_markup=main_kb)
        await callback.answer()

    @dp.callback_query(F.data == "main_menu_return")
    async def main_menu_return(callback: types.CallbackQuery, state: FSMContext):
        # При возврате назад просто вызываем старт
        from handlers.main_menu import cmd_start
        await cmd_start(callback.message, state, bot) 
        await callback.answer()

    @dp.callback_query(F.data == "back_to_start")
    async def back_to_start_handler(callback: types.CallbackQuery, state: FSMContext):
        # Возврат к стартовому сообщению
        from handlers.main_menu import cmd_start
        await cmd_start(callback.message, state, bot)
        await callback.answer()

    @dp.callback_query(F.data == "ignore")
    async def ignore_click(callback: types.CallbackQuery):
        await callback.answer()

    @dp.callback_query(F.data == "report")
    async def report_click(callback: types.CallbackQuery):
        await callback.answer("✅ Жалоба отправлена администрации", show_alert=True)

    @dp.callback_query(F.data.startswith("page_"))
    async def process_pagination(callback: types.CallbackQuery, state: FSMContext):
        parts = callback.data.split("_")
        mode = parts[1]
        
        if mode == "earn":
            task_type = parts[2]
            page = int(parts[3])
            await show_earn_list(callback, state, bot, task_type, page)
        elif mode == "myads":
            page = int(parts[2])
            await show_my_ads_page(callback, state, bot, page)
        
        # Восстанавливаем клавиатуру после пагинации
        await restore_keyboard(callback.message.chat.id, bot)
        await callback.answer()

