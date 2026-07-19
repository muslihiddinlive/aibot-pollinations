from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, MessageEntity
from aiogram.fsm.context import FSMContext

from config import SUPERADMIN_ID
from state import store
from codes import generate_code
from keyboards import admin_panel, cancel_kb
from states import GenCode, GrantLimit, Broadcast, WordsManage, EmojiManage

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id == SUPERADMIN_ID or user_id in store.data.get("admins", [])


def is_superadmin(user_id: int) -> bool:
    return user_id == SUPERADMIN_ID


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 Admin panel:", reply_markup=admin_panel())


@router.callback_query(F.data == "adm_cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("🛠 Admin panel:", reply_markup=admin_panel())
    await call.answer()


# ---------- Userlar ----------

@router.callback_query(F.data == "adm_users")
async def cb_users(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    users = store.data["users"]
    if not users:
        await call.message.answer("Hozircha userlar yo'q.")
        return await call.answer()

    lines = []
    for uid, u in list(users.items())[:50]:
        left = store.remaining_limit(int(uid))
        last_prompts = ", ".join(p["prompt"][:20] for p in u["prompts"][-3:]) or "—"
        lines.append(
            f"👤 {u.get('username') or '—'} [id: {uid}] | qolgan: {left}\n   so'nggi promptlar: {last_prompts}"
        )
    text = "👥 Userlar (oxirgi 50 tasi):\n\n" + "\n\n".join(lines)
    for i in range(0, len(text), 3500):
        await call.message.answer(text[i:i + 3500])
    await call.answer()


# ---------- Broadcast ----------

@router.callback_query(F.data == "adm_broadcast")
async def cb_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(Broadcast.waiting_text)
    await call.message.answer("Barcha userlarga yuboriladigan xabar matnini kiriting:", reply_markup=cancel_kb())
    await call.answer()


@router.message(Broadcast.waiting_text)
async def do_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    sent, failed = 0, 0
    for uid in store.data["users"].keys():
        try:
            await bot.send_message(int(uid), message.text)
            sent += 1
        except Exception:
            failed += 1
    await message.answer(f"📢 Yuborildi: {sent} ta, xato: {failed} ta.")


# ---------- Limit berish (kodsiz, to'g'ridan-to'g'ri) ----------

@router.callback_query(F.data == "adm_grant")
async def cb_grant(call: CallbackQuery, state: FSMContext):
    if not is_superadmin(call.from_user.id):
        return await call.answer("Faqat superadmin uchun.", show_alert=True)
    await state.set_state(GrantLimit.waiting_user)
    await call.message.answer("Kimga limit berasiz? User ID'sini yuboring:", reply_markup=cancel_kb())
    await call.answer()


@router.message(GrantLimit.waiting_user)
async def grant_user(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Noto'g'ri ID. Raqam yuboring.")
    await state.update_data(user_id=uid)
    await state.set_state(GrantLimit.waiting_amount)
    await message.answer("Nechta rasm limiti qo'shilsin (sutkasiga)?")


@router.message(GrantLimit.waiting_amount)
async def grant_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Raqam kiriting.")
    await state.update_data(amount=amount)
    await state.set_state(GrantLimit.waiting_days)
    await message.answer("Necha kunga beriladi?")


@router.message(GrantLimit.waiting_days)
async def grant_days(message: Message, state: FSMContext, bot: Bot):
    try:
        days = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Raqam kiriting.")
    data = await state.get_data()
    await state.clear()
    store.grant_limit(data["user_id"], data["amount"], days)
    await store.save(bot)
    await message.answer(f"✅ User {data['user_id']} ga +{data['amount']} limit, {days} kunga berildi.")
    try:
        await bot.send_message(
            data["user_id"],
            f"🎁 Sizga admin tomonidan +{data['amount']} ta qo'shimcha limit berildi ({days} kunga amal qiladi)."
        )
    except Exception:
        pass


# ---------- Bir martalik kod yaratish ----------

@router.callback_query(F.data == "adm_gencode")
async def cb_gencode(call: CallbackQuery, state: FSMContext):
    if not is_superadmin(call.from_user.id):
        return await call.answer("Faqat superadmin uchun.", show_alert=True)
    await state.set_state(GenCode.waiting_amount)
    await call.message.answer("Kod qancha limit (sutkasiga nechta rasm) qo'shsin?", reply_markup=cancel_kb())
    await call.answer()


@router.message(GenCode.waiting_amount)
async def gencode_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Raqam kiriting.")
    await state.update_data(amount=amount)
    await state.set_state(GenCode.waiting_days)
    await message.answer("Necha kunga amal qiladi? (kunlarda)")


@router.message(GenCode.waiting_days)
async def gencode_days(message: Message, state: FSMContext, bot: Bot):
    try:
        days = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Raqam kiriting.")
    data = await state.get_data()
    await state.clear()

    code = generate_code()
    store.data["codes"][code] = {
        "limit_add": data["amount"],
        "days": days,
        "used": False,
    }
    await store.save(message.bot)
    await message.answer(
        f"✅ Kod yaratildi:\n\n`{code}`\n\n+{data['amount']} limit, {days} kunga, bir martalik.",
        parse_mode="Markdown",
    )


# ---------- Taqiqlangan so'zlar ----------

@router.callback_query(F.data == "adm_words")
async def cb_words(call: CallbackQuery):
    if not is_superadmin(call.from_user.id):
        return await call.answer("Faqat superadmin uchun.", show_alert=True)
    from config import BANNED_WORDS
    extra = store.data.get("banned_words", [])
    text = (
        "🚫 Asosiy ro'yxat: " + ", ".join(BANNED_WORDS) + "\n"
        "➕ Qo'shimcha: " + (", ".join(extra) if extra else "—") + "\n\n"
        "Qo'shish uchun: /addword [so'z]\n"
        "O'chirish uchun: /delword [so'z]"
    )
    await call.message.answer(text)
    await call.answer()


@router.message(Command("addword"))
async def addword(message: Message, command: Command, bot: Bot):
    if not is_superadmin(message.from_user.id):
        return
    word = message.text.partition(" ")[2].strip()
    if not word:
        return await message.answer("Foydalanish: /addword [so'z]")
    store.data.setdefault("banned_words", [])
    if word not in store.data["banned_words"]:
        store.data["banned_words"].append(word)
        await store.save(bot)
    await message.answer(f"✅ Qo'shildi: {word}")


@router.message(Command("delword"))
async def delword(message: Message, bot: Bot):
    if not is_superadmin(message.from_user.id):
        return
    word = message.text.partition(" ")[2].strip()
    if word in store.data.get("banned_words", []):
        store.data["banned_words"].remove(word)
        await store.save(bot)
        await message.answer(f"✅ O'chirildi: {word}")
    else:
        await message.answer("Bu so'z qo'shimcha ro'yxatda topilmadi (asosiy ro'yxatdagi so'zlar o'chirilmaydi).")


# ---------- Custom (premium) emoji ----------

@router.callback_query(F.data == "adm_emoji")
async def cb_emoji(call: CallbackQuery, state: FSMContext):
    if not is_superadmin(call.from_user.id):
        return await call.answer("Faqat superadmin uchun.", show_alert=True)
    emojis = store.data.get("custom_emojis", {})
    text = "😀 Custom emoji ro'yxati:\n" + (
        "\n".join(f"- {k}: {v}" for k, v in emojis.items()) or "—"
    )
    text += "\n\nQo'shish: /addemoji [kalit] [custom_emoji_id]\nO'chirish: /delemoji [kalit]"
    await call.message.answer(text)
    await call.answer()


@router.message(Command("addemoji"))
async def addemoji(message: Message, bot: Bot):
    if not is_superadmin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return await message.answer("Foydalanish: /addemoji [kalit] [custom_emoji_id]")
    key, emoji_id = parts[1], parts[2]
    store.data.setdefault("custom_emojis", {})[key] = emoji_id
    await store.save(bot)
    # namuna sifatida shu emojini darhol ko'rsatib beramiz
    try:
        await message.answer(
            "🙂",
            entities=[MessageEntity(type="custom_emoji", offset=0, length=1, custom_emoji_id=emoji_id)],
        )
    except Exception:
        pass
    await message.answer(f"✅ Qo'shildi: {key} -> {emoji_id}")


@router.message(Command("delemoji"))
async def delemoji(message: Message, bot: Bot):
    if not is_superadmin(message.from_user.id):
        return
    key = message.text.partition(" ")[2].strip()
    if key in store.data.get("custom_emojis", {}):
        del store.data["custom_emojis"][key]
        await store.save(bot)
        await message.answer(f"✅ O'chirildi: {key}")
    else:
        await message.answer("Topilmadi.")


# ---------- Premium reaksiya adminlari ----------

@router.callback_query(F.data == "adm_reactions")
async def cb_reactions(call: CallbackQuery):
    if not is_superadmin(call.from_user.id):
        return await call.answer("Faqat superadmin uchun.", show_alert=True)
    admins = store.data.get("reaction_admins", [])
    text = (
        "⭐️ Premium reaksiya bosiladigan adminlar: " + (", ".join(map(str, admins)) or "—") + "\n\n"
        "Qo'shish: /addreactionadmin [user_id]\n"
        "O'chirish: /delreactionadmin [user_id]\n"
        "Reaksiya emoji ID: /setreactionemoji [custom_emoji_id]"
    )
    await call.message.answer(text)
    await call.answer()


@router.message(Command("addreactionadmin"))
async def add_reaction_admin(message: Message, bot: Bot):
    if not is_superadmin(message.from_user.id):
        return
    try:
        uid = int(message.text.partition(" ")[2].strip())
    except ValueError:
        return await message.answer("Foydalanish: /addreactionadmin [user_id]")
    lst = store.data.setdefault("reaction_admins", [])
    if uid not in lst:
        lst.append(uid)
        await store.save(bot)
    await message.answer(f"✅ Qo'shildi: {uid}")


@router.message(Command("delreactionadmin"))
async def del_reaction_admin(message: Message, bot: Bot):
    if not is_superadmin(message.from_user.id):
        return
    try:
        uid = int(message.text.partition(" ")[2].strip())
    except ValueError:
        return await message.answer("Foydalanish: /delreactionadmin [user_id]")
    lst = store.data.setdefault("reaction_admins", [])
    if uid in lst:
        lst.remove(uid)
        await store.save(bot)
        await message.answer(f"✅ O'chirildi: {uid}")
    else:
        await message.answer("Topilmadi.")


@router.message(Command("setreactionemoji"))
async def set_reaction_emoji(message: Message, bot: Bot):
    if not is_superadmin(message.from_user.id):
        return
    emoji_id = message.text.partition(" ")[2].strip()
    if not emoji_id:
        return await message.answer("Foydalanish: /setreactionemoji [custom_emoji_id]")
    store.data["reaction_emoji_id"] = emoji_id
    await store.save(bot)
    await message.answer("✅ Reaksiya emoji o'rnatildi.")


# ---------- Admin qo'shish/olib tashlash (kim panelga kira oladi) ----------

@router.message(Command("addadmin"))
async def add_admin(message: Message, bot: Bot):
    if not is_superadmin(message.from_user.id):
        return
    try:
        uid = int(message.text.partition(" ")[2].strip())
    except ValueError:
        return await message.answer("Foydalanish: /addadmin [user_id]")
    lst = store.data.setdefault("admins", [])
    if uid not in lst:
        lst.append(uid)
        await store.save(bot)
    await message.answer(f"✅ Admin qo'shildi: {uid}")


@router.message(Command("deladmin"))
async def del_admin(message: Message, bot: Bot):
    if not is_superadmin(message.from_user.id):
        return
    try:
        uid = int(message.text.partition(" ")[2].strip())
    except ValueError:
        return await message.answer("Foydalanish: /deladmin [user_id]")
    lst = store.data.setdefault("admins", [])
    if uid in lst:
        lst.remove(uid)
        await store.save(bot)
        await message.answer(f"✅ Admin o'chirildi: {uid}")
    else:
        await message.answer("Topilmadi.")
