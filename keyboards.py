from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🎨 Rasm yaratish"), KeyboardButton(text="📊 Limitim")],
        [KeyboardButton(text="🔑 Kod kiritish"), KeyboardButton(text="🏆 Reyting")],
        [KeyboardButton(text="💳 Tarif sotib olish"), KeyboardButton(text="✉️ Adminga murojaat")],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 Admin panel")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admusers")],
        [InlineKeyboardButton(text="📢 Habar yuborish (broadcast)", callback_data="admbroadcast")],
        [InlineKeyboardButton(text="🔑 Kod yaratish", callback_data="admgencode")],
        [InlineKeyboardButton(text="🚫 Taqiqlangan so'zlar", callback_data="admwords")],
        [InlineKeyboardButton(text="😀 Custom emoji", callback_data="admemoji")],
        [InlineKeyboardButton(text="✏️ Xabarni emoji bilan tahrirlash", callback_data="admeditemoji")],
        [InlineKeyboardButton(text="⭐️ Premium reaksiya adminlari", callback_data="admreactions")],
        [InlineKeyboardButton(text="🛠 Adminlar (superadmin)", callback_data="admmanageadmins")],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admcancel")]
    ])


def users_list_kb(users: dict, page: int = 0, per_page: int = 15) -> InlineKeyboardMarkup:
    items = list(users.items())
    start = page * per_page
    chunk = items[start:start + per_page]
    rows = []
    for uid, u in chunk:
        label = f"👤 {u.get('username') or uid} | 🖼{u.get('images_generated', 0)}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"admuser:{uid}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admuserspage:{page - 1}"))
    if start + per_page < len(items):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admuserspage:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="❌ Yopish", callback_data="admcancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_detail_kb(uid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Limit berish", callback_data=f"admgrantopen:{uid}")],
        [InlineKeyboardButton(text="🖼 Yaratgan rasmlari", callback_data=f"admimgs:{uid}")],
        [InlineKeyboardButton(text="✉️ Xabar yozish", callback_data=f"admmsguser:{uid}")],
        [InlineKeyboardButton(text="🚫 Ban/Unban", callback_data=f"admban:{uid}")],
        [InlineKeyboardButton(text="🔙 Ro'yxatga", callback_data="admusers")],
    ])


def grant_type_kb(uid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔂 Bir martalik (doimiy qo'shiladi)", callback_data=f"admgrant:onetime:{uid}")],
        [InlineKeyboardButton(text="📅 Kunlik limit (muddatli)", callback_data=f"admgrant:daily:{uid}")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admcancel")],
    ])


def gencode_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔂 Bir martalik (doimiy qo'shiladi)", callback_data="admgencodetype:onetime")],
        [InlineKeyboardButton(text="📅 Kunlik limit (muddatli)", callback_data="admgencodetype:daily")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admcancel")],
    ])


def manage_admins_kb(admins: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"❌ {a}", callback_data=f"admdeladmin:{a}")] for a in admins]
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admcancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
