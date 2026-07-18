from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎨 Rasm yaratish"), KeyboardButton(text="📊 Limitim")],
            [KeyboardButton(text="🔑 Kod kiritish"), KeyboardButton(text="💳 Tarif sotib olish")],
        ],
        resize_keyboard=True,
    )


def admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Userlar", callback_data="adm_users")],
        [InlineKeyboardButton(text="📢 Habar yuborish (broadcast)", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🎁 Limit berish (userga)", callback_data="adm_grant")],
        [InlineKeyboardButton(text="🔑 Bir martalik kod yaratish", callback_data="adm_gencode")],
        [InlineKeyboardButton(text="🚫 Taqiqlangan so'zlar", callback_data="adm_words")],
        [InlineKeyboardButton(text="😀 Custom emoji", callback_data="adm_emoji")],
        [InlineKeyboardButton(text="⭐️ Premium reaksiya adminlari", callback_data="adm_reactions")],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_cancel")]
    ])
