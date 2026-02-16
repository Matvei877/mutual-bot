import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from database import db_complete_task_immediate, db_get_review, db_delete_review, db_update_balance
from config import ADMIN_IDS, CURRENCY_NAME

logger = logging.getLogger(__name__)

def register_admin_handlers(dp: Dispatcher, bot: Bot):
    @dp.message(Command("give"))
    async def cmd_admin_give(message: types.Message):
        if message.from_user.id not in ADMIN_IDS: return
        try:
            parts = message.text.split()
            if len(parts) < 3: return
            user_id = int(parts[1])
            amount = float(parts[2])
            
            await db_update_balance(user_id, amount, tx_type='admin_bonus', description='🎁 Бонус админа', is_earned=False)
            await bot.send_message(user_id, f"🎁 Админ начислил вам <b>{int(amount)} {CURRENCY_NAME}</b>!", parse_mode="HTML")
        except Exception as e:
            pass

    @dp.callback_query(F.data.startswith("admin_approve_"))
    async def process_admin_approve(callback: types.CallbackQuery):
        review_id = int(callback.data.split("_")[2])
        
        review_data = await db_get_review(review_id)
        if not review_data:
            await callback.answer("❌ Заявка не найдена (возможно, уже обработана)", show_alert=True)
            try: await callback.message.delete()
            except: pass
            return

        user_id = review_data['user_id']
        task_id = review_data['task_id']
        
        success, msg = await db_complete_task_immediate(user_id, task_id)
        
        if success:
            try:
                await bot.send_message(user_id, f"✅ <b>Ваш скриншот принят!</b>\nЗадание #{task_id} выполнено.\n{msg}", parse_mode="HTML")
            except: pass
            
            await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n✅ <b>ОДОБРЕНО</b> администратором.")
            await db_delete_review(review_id)
        else:
            await callback.answer(f"❌ Не удалось завершить задачу: {msg}", show_alert=True)

    @dp.callback_query(F.data.startswith("admin_reject_"))
    async def process_admin_reject(callback: types.CallbackQuery):
        review_id = int(callback.data.split("_")[2])
        
        review_data = await db_get_review(review_id)
        if not review_data:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return

        user_id = review_data['user_id']
        
        try:
            await bot.send_message(user_id, f"❌ <b>Ваш скриншот отклонен!</b>\nЗадание не засчитано.", parse_mode="HTML")
        except: pass
        
        await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n❌ <b>ОТКЛОНЕНО</b> администратором.")
        await db_delete_review(review_id)

