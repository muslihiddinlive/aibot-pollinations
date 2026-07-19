from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🎨 Rasm yaratish"), KeyboardButton(text="📊 Limitim")],
        [KeyboardButton(text="🔑 Kod kiritish"), KeyboardButton(text="🏆 Reyting")],
        [KeyboardButton(text="💳 Tarif sotib olish"), KeyboardButton(text="🔗 Referal havolam")],
        [KeyboardButton(text="✉️ Adminga murojaat")],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 Admin panel")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admusers")],
        [InlineKeyboardButton(text="📢 Habar yuborish (broadcast)", callback_data="admbroadcast")],
        [InlineKeyboardButton(text="🔑 Tarif-kod yaratish", callback_data="admgencode")],
        [InlineKeyboardButton(text="💳 Tariflar sozlamasi", callback_data="admtariffs")],
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
        [InlineKeyboardButton(text="🎫 Tarif berish", callback_data=f"admgrantopen:{uid}")],
        [InlineKeyboardButton(text="🖼 Yaratgan rasmlari", callback_data=f"admimgs:{uid}")],
        [InlineKeyboardButton(text="✉️ Xabar yozish", callback_data=f"admmsguser:{uid}")],
        [InlineKeyboardButton(text="🚫 Ban/Unban", callback_data=f"admban:{uid}")],
        [InlineKeyboardButton(text="🔙 Ro'yxatga", callback_data="admusers")],
    ])


def tariff_choice_kb(callback_prefix: str, tariffs: list, uid: str = "") -> InlineKeyboardMarkup:
    """callback_prefix: masalan 'admgrant' yoki 'admgencodetariff'.
    tariffs: shu adminga ruxsat etilgan tarif nomlari ro'yxati."""
    from config import TARIFF_LABELS
    suffix = f":{uid}" if uid else ""
    rows = [
        [InlineKeyboardButton(text=TARIFF_LABELS.get(t, t), callback_data=f"{callback_prefix}:{t}{suffix}")]
        for t in tariffs
    ]
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admcancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manage_admins_kb(admins: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"❌ {a}", callback_data=f"admdeladmin:{a}")] for a in admins]
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admcancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tariff_purchase_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Pro so'rash", callback_data="tariffreq:pro")],
        [InlineKeyboardButton(text="💎 Plus so'rash", callback_data="tariffreq:plus")],
        [InlineKeyboardButton(text="👑 VIP so'rash", callback_data="tariffreq:vip")],
    ])
