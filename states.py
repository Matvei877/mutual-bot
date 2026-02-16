from aiogram.fsm.state import State, StatesGroup

class AppStates(StatesGroup):
    waiting_ad_link = State()
    waiting_ad_count = State()
    waiting_ad_price = State()
    waiting_stars_amount = State()
    waiting_proof_screenshot = State()

