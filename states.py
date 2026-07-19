from aiogram.fsm.state import State, StatesGroup


class GenCode(StatesGroup):
    """Superadmin panelidan kod yaratish. Tur (bir martalik/kunlik) inline
    tugma orqali FSM data'ga yoziladi, keyin shu state'lar ishga tushadi."""
    waiting_amount = State()
    waiting_days = State()  # faqat "daily" turi uchun


class DirectGrant(StatesGroup):
    """Foydalanuvchi kartochkasidan to'g'ridan-to'g'ri (kodsiz) limit berish."""
    waiting_amount = State()
    waiting_days = State()  # faqat "daily" turi uchun


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
