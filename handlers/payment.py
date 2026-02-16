import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton
from utils import send_clean_message
from database import db_update_balance, db_add_invoice
from keyboards import get_stars_amounts_kb, get_cancel_kb, get_deposit_kb
from states import AppStates
from config import CURRENCY_NAME, STARS_TO_FCOINS_RATE

logger = logging.getLogger(__name__)

def register_payment_handlers(dp: Dispatcher, bot: Bot):
    @dp.callback_query(F.data == "back_to_profile_cb")
    async def back_to_profile_cb(callback: types.CallbackQuery, state: FSMContext):
        from database import db_get_user
        balance, earned_balance = await db_get_user(callback.from_user.id)
        total = balance + earned_balance
        
        from utils import safe_edit_message
        await safe_edit_message(
            callback.message, state, bot,
            f"👤 <b>Ваш кабинет</b>\n\n"
            f"🆔 ID: <code>{callback.from_user.id}</code>\n"
            f"💳 Пополнено: <b>{int(balance)} {CURRENCY_NAME}</b>\n"
            f"⚒️ Заработано: <b>{int(earned_balance)} {CURRENCY_NAME}</b>\n"
            f"💰 Всего: <b>{int(total)} {CURRENCY_NAME}</b>\n\n"
            f"Пополнить баланс можно через Telegram Stars.",
            reply_markup=get_deposit_kb()
        )
        await callback.answer()

    # --- ПОПОЛНЕНИЕ ---

    @dp.callback_query(F.data == "topup_stars")
    async def topup_stars_menu(callback: types.CallbackQuery, state: FSMContext):
        from utils import safe_edit_message
        await safe_edit_message(
            callback.message, state, bot,
            f"⭐ <b>Пополнение {CURRENCY_NAME}</b>\n\n"
            f"Курс: 1 ⭐ = {int(STARS_TO_FCOINS_RATE)} {CURRENCY_NAME}\n\n"
            f"Выберите количество звезд для оплаты:",
            reply_markup=get_stars_amounts_kb()
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("stars_") & (F.data != "stars_custom"))
    async def process_stars_fixed(callback: types.CallbackQuery, state: FSMContext):
        stars_amount = int(callback.data.split("_")[1])
        await create_stars_invoice(callback.message, stars_amount, callback.from_user.id, bot)
        await callback.answer()

    @dp.callback_query(F.data == "stars_custom")
    async def process_stars_custom(callback: types.CallbackQuery, state: FSMContext):
        await send_clean_message(
            callback.message, state, bot,
            f"Введите количество Stars (минимум 1):\n"
            f"Вы получите кол-во Stars × {int(STARS_TO_FCOINS_RATE)} {CURRENCY_NAME}",
            reply_markup=get_cancel_kb()
        )
        await state.set_state(AppStates.waiting_stars_amount)
        await callback.answer()

    @dp.message(AppStates.waiting_stars_amount)
    async def process_stars_custom_amount(message: types.Message, state: FSMContext):
        try:
            stars_amount = int(message.text)
            if stars_amount < 1:
                await send_clean_message(message, state, bot, "❌ Минимум 1 Star")
                return
            if stars_amount > 10000:
                await send_clean_message(message, state, bot, "❌ Слишком много за раз")
                return
            
            await create_stars_invoice(message, stars_amount, message.from_user.id, bot)
            await state.set_state(None)
        except ValueError:
            await send_clean_message(message, state, bot, "❌ Введите целое число")

    async def create_stars_invoice(message: types.Message, stars_amount: int, user_id: int, bot: Bot):
        try:
            fcoins_amount = stars_amount * STARS_TO_FCOINS_RATE
            payload = f"stars_{user_id}_{message.message_id}_{stars_amount}"
            
            prices = [LabeledPrice(label=f"{int(fcoins_amount)} {CURRENCY_NAME}", amount=stars_amount)]
            
            await bot.send_invoice(
                chat_id=user_id,
                title=f"Покупка {CURRENCY_NAME}",
                description=f"Пополнение на {int(fcoins_amount)} {CURRENCY_NAME}",
                payload=payload,
                currency="XTR",
                prices=prices,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Оплатить {stars_amount} ⭐", pay=True)]])
            )
            await db_add_invoice(payload, user_id, fcoins_amount)
            
        except Exception as e:
            logger.error(f"Error invoice: {e}")
            await message.answer("❌ Ошибка создания счета")

    @dp.pre_checkout_query()
    async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

    @dp.message(F.successful_payment)
    async def process_successful_payment(message: types.Message):
        try:
            stars_paid = message.successful_payment.total_amount
            fcoins_amount = stars_paid * STARS_TO_FCOINS_RATE
            user_id = message.from_user.id
            
            await db_update_balance(
                user_id, 
                fcoins_amount,
                tx_type='deposit_stars',
                description=f'Покупка за {stars_paid} Stars',
                is_earned=False
            )
            
            await message.answer(
                f"✅ <b>Оплата прошла успешно!</b>\n\n"
                f"⭐ Списано: {stars_paid} Stars\n"
                f"💰 Зачислено: <b>{int(fcoins_amount)} {CURRENCY_NAME}</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Payment error: {e}")

