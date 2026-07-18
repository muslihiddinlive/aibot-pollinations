from aiogram.fsm.state import State, StatesGroup


class GenCode(StatesGroup):
    waiting_amount = State()
    waiting_days = State()


class GrantLimit(StatesGroup):
    waiting_user = State()
    waiting_amount = State()
    waiting_days = State()


class Broadcast(StatesGroup):
    waiting_text = State()


class WordsManage(StatesGroup):
    waiting_add = State()
    waiting_remove = State()


class EmojiManage(StatesGroup):
    waiting_add_key = State()
    waiting_add_id = State()
    waiting_remove_key = State()


class RequestTariff(StatesGroup):
    waiting_message = State()
