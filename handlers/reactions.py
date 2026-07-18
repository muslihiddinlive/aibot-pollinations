from aiogram import Router, Bot, F
from aiogram.types import Message, ReactionTypeCustomEmoji, ReactionTypeEmoji

from config import SUPERADMIN_ID
from state import store

router = Router()


# MUHIM: bu router main.py da ENG OXIRIDA ulanadi va faqat group/supergroup
# xabarlariga filtrlanadi, shunda boshqa handlerlar undan oldin ishlab
# ulguradi va bu handler ularni "yutib" yubormaydi.
@router.message(F.chat.type.in_({"group", "supergroup"}))
async def react_to_admins(message: Message, bot: Bot):
    """
    Superadmin yoki u tanlagan adminlar guruh/kanalda xabar yozsa,
    bot shu xabarga premium (custom emoji) reaksiya bosadi.
    Eslatma: reaksiya turi shu chatda ruxsat etilgan bo'lishi kerak,
    aks holda Telegram xato qaytarishi mumkin - shu sababli try/except bilan o'ralgan.
    """
    if not message.from_user:
        return

    reaction_admins = set(store.data.get("reaction_admins", [])) | {SUPERADMIN_ID}
    if message.from_user.id not in reaction_admins:
        return

    emoji_id = store.data.get("reaction_emoji_id")
    try:
        if emoji_id:
            await bot.set_message_reaction(
                chat_id=message.chat.id,
                message_id=message.message_id,
                reaction=[ReactionTypeCustomEmoji(custom_emoji_id=emoji_id)],
            )
        else:
            await bot.set_message_reaction(
                chat_id=message.chat.id,
                message_id=message.message_id,
                reaction=[ReactionTypeEmoji(emoji="🔥")],
            )
    except Exception as e:
        print(f"[reactions] reaksiya qo'yib bo'lmadi: {e}")
