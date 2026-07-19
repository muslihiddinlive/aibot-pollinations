from aiogram.fsm.state import State, StatesGroup


class GenCode(StatesGroup):
    """Superadmin panelidan tarif-kod yaratish. Tarif inline tugma orqali FSM
    data'ga yoziladi, so'ng shu state kutiladi (kunlar soni)."""
    waiting_days = State()


class TariffGrant(StatesGroup):
    """Foydalanuvchi kartochkasidan to'g'ridan-to'g'ri tarif berish."""
    waiting_days = State()


class Broadcast(StatesGroup):
    waiting_text = State()


class SendToUser(StatesGroup):
    """Admin muayyan userga shaxsiy xabar yozadi."""
    waiting_text = State()


class WordsManage(StatesGroup):
    waiting_add = State()
    waiting_remove = State()


class EmojiManage(StatesGroup):
    waiting_add_key = State()
    waiting_add_id = State()
    waiting_remove_key = State()


class EditMessageEmoji(StatesGroup):
    """Bot o'zi yuborgan xabarni premium emoji bilan qayta tahrirlash."""
    waiting_target = State()   # "chat_id:message_id"
    waiting_text = State()     # {key} placeholderlar bilan matn


class RequestTariff(StatesGroup):
    waiting_message = State()


class UserContact(StatesGroup):
    """Oddiy foydalanuvchi "Adminga murojaat" tugmasi orqali yozadi."""
    waiting_message = State()
