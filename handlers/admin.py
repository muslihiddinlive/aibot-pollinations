from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, MessageEntity
from aiogram.fsm.context import FSMContext

from config import SUPERADMIN_ID
from state import store, UNLIMITED
from codes import generate_code
from keyboards import (
    admin_panel, cancel_kb, users_list_kb, user_detail_kb,
    grant_type_kb, gencode_type_kb, manage_admins_kb,
)
from states import (
    GenCode, DirectGrant, Broadcast, WordsManage, EmojiManage,
    SendToUser, EditMessageEmoji,
)
from emoji_utils import build_emoji_entities

router = Router()


def is_admin(user_id: int) -> bool:
    return store.is_admin_user(user_id)


def is_superadmin(user_id: int) -> bool:
    """Faqat asosiy egasi - adminlarni tayinlash/olib tashlash shu darajaga tegishli."""
    return user_id == SUPERADMIN_ID


def _fmt_limit(uid: int) -> str:
    left = store.remaining_limit(uid)
    return "♾ Cheksiz" if left >= UNLIMITED else str(left)


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(
        f"🆔 Sizning Telegram ID'ingiz: <code>{message.from_user.id}</code>\n\n"
        f"Superadmin bo'lish uchun shu raqamni Render'dagi <code>SUPERADMIN_ID</code> "
        f"environment variable'iga qo'yib, xizmatni qayta deploy qiling."
    )


@router.message(Command("admin"))
@router.message(F.text == "🛠 Admin panel")
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        await message.answer(
            "🚫 Sizda admin panelga ruxsat yo'q.\n"
            f"Sizning ID: <code>{message.from_user.id}</code>\n"
            "Bu ID Render'dagi SUPERADMIN_ID bilan (yoki /addadmin orqali qo'shilgan adminlar ro'yxati bilan) mos kelmayapti."
        )
        return
    await message.answer("🛠 Admin panel:", reply_markup=admin_panel())


@router.callback_query(F.data == "admcancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("🛠 Admin panel:", reply_markup=admin_panel())
    await call.answer()


# ---------- Userlar ro'yxati va kartochkasi ----------

@router.callback_query(F.data == "admusers")
async def cb_users(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    users = store.data["users"]
    if not users:
        await call.message.edit_text("Hozircha userlar yo'q.", reply_markup=cancel_kb())
        return await call.answer()
    await call.message.edit_text(
        f"👥 Userlar ({len(users)} ta). Batafsil ko'rish uchun bosing:",
        reply_markup=users_list_kb(users, page=0),
    )
    await call.answer()


@router.callback_query(F.data.startswith("admuserspage:"))
async def cb_users_page(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    page = int(call.data.split(":")[1])
    users = store.data["users"]
    await call.message.edit_text(
        f"👥 Userlar ({len(users)} ta). Batafsil ko'rish uchun bosing:",
        reply_markup=users_list_kb(users, page=page),
    )
    await call.answer()


async def _render_user_detail(call: CallbackQuery, uid: str):
    users = store.data["users"]
    u = users.get(uid)
    if not u:
        return await call.message.edit_text("Topilmadi.", reply_markup=cancel_kb())
    left = _fmt_limit(int(uid))
    tariff = f"kunlik {u.get('daily_limit', 0)} + qo'shimcha {u.get('extra_limit', 0)}"
    if u.get("extra_limit_until"):
        tariff += f" ({u['extra_limit_until']} gacha)"
    ban_text = "ha" if u.get("banned") else "yo'q"
    text = (
        f"👤 <b>{u.get('username') or '—'}</b>\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"📅 Qo'shilgan: {u.get('first_seen', '—')}\n"
        f"🖼 Yaratgan rasmlar: {u.get('images_generated', 0)}\n"
        f"💳 Tarif: {tariff}\n"
        f"⏳ Hozir qolgan limit: {left}\n"
        f"🚫 Ban: {ban_text}"
    )
    await call.message.edit_text(text, reply_markup=user_detail_kb(uid))


@router.callback_query(F.data.startswith("admuser:"))
async def cb_user_detail(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    uid = call.data.split(":", 1)[1]
    await _render_user_detail(call, uid)
    await call.answer()


@router.callback_query(F.data.startswith("admban:"))
async def cb_toggle_ban(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return await call.answer()
    uid = call.data.split(":", 1)[1]
    u = store.data["users"].get(uid)
    if not u:
        return await call.answer("Topilmadi.", show_alert=True)
    u["banned"] = not u.get("banned", False)
    store.schedule_save(bot)
    await _render_user_detail(call, uid)
    await call.answer("✅ Yangilandi.")


@router.callback_query(F.data.startswith("admimgs:"))
async def cb_user_images(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return await call.answer()
    uid = call.data.split(":", 1)[1]
    u = store.data["users"].get(uid)
    if not u or not u.get("generated_images"):
        await call.answer("Bu user hali rasm yaratmagan.", show_alert=True)
        return
    await call.answer()
    for img in u["generated_images"][-6:]:
        try:
            await bot.send_photo(
                call.from_user.id, img["file_id"],
                caption=f"📝 {img['prompt'][:200]}\n🗓 {img['at']}",
            )
        except Exception as e:
            print(f"[admin] userimages yuborishda xato: {e}")


@router.callback_query(F.data.startswith("admmsguser:"))
async def cb_msg_user(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    uid = call.data.split(":", 1)[1]
    await state.set_state(SendToUser.waiting_text)
    await state.update_data(target_uid=int(uid))
    await call.message.answer(f"✍️ [{uid}] ga yuboriladigan xabarni yozing:", reply_markup=cancel_kb())
    await call.answer()


@router.message(SendToUser.waiting_text)
async def do_msg_user(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    target = data.get("target_uid")
    try:
        await bot.send_message(target, f"📩 Admindan xabar:\n\n{message.text}")
        await message.answer("✅ Yuborildi.")
    except Exception as e:
        await message.answer(f"❌ Yuborib bo'lmadi: {e}")


# ---------- Limit berish (userga, kodsiz) ----------

@router.callback_query(F.data.startswith("admgrantopen:"))
async def cb_grant_open(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    uid = call.data.split(":", 1)[1]
    await call.message.edit_text("Limit turini tanlang:", reply_markup=grant_type_kb(uid))
    await call.answer()


@router.callback_query(F.data.startswith("admgrant:"))
async def cb_grant_type(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    _, gtype, uid = call.data.split(":", 2)
    await state.set_state(DirectGrant.waiting_amount)
    await state.update_data(target_uid=int(uid), grant_type=gtype)
    await call.message.answer("Nechta rasm limiti qo'shilsin?", reply_markup=cancel_kb())
    await call.answer()


@router.message(DirectGrant.waiting_amount)
async def direct_grant_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Raqam kiriting.")
    data = await state.get_data()
    if data.get("grant_type") == "onetime":
        store.grant_permanent(data["target_uid"], amount)
        store.schedule_save(bot)
        await state.clear()
        await message.answer(f"✅ User {data['target_uid']} ga +{amount} limit doimiy qo'shildi.")
        try:
            await bot.send_message(data["target_uid"], f"🎁 Sizga +{amount} ta doimiy limit berildi.")
        except Exception:
            pass
        return
    await state.update_data(amount=amount)
    await state.set_state(DirectGrant.waiting_days)
    await message.answer("Necha kunga amal qiladi?")


@router.message(DirectGrant.waiting_days)
async def direct_grant_days(message: Message, state: FSMContext, bot: Bot):
    try:
        days = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Raqam kiriting.")
    data = await state.get_data()
    await state.clear()
    store.grant_limit(data["target_uid"], data["amount"], days)
    store.schedule_save(bot)
    await message.answer(f"✅ User {data['target_uid']} ga +{data['amount']} limit, {days} kunga berildi.")
    try:
        await bot.send_message(
            data["target_uid"],
            f"🎁 Sizga +{data['amount']} ta qo'shimcha limit berildi ({days} kunga amal qiladi).",
        )
    except Exception:
        pass


# ---------- Broadcast ----------

@router.callback_query(F.data == "admbroadcast")
async def cb_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(Broadcast.waiting_text)
    await call.message.answer("Barcha userlarga yuboriladigan xabar matnini kiriting:", reply_markup=cancel_kb())
    await call.answer()


@router.message(Broadcast.waiting_text)
async def do_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    if not message.text:
        return await message.answer("❌ Matn yuboring.")
    sent, failed = 0, 0
    for uid in store.data["users"].keys():
        try:
            await bot.send_message(int(uid), message.text)
            sent += 1
        except Exception:
            failed += 1
    await message.answer(f"📢 Yuborildi: {sent} ta, xato: {failed} ta.")


# ---------- Kod yaratish (bir martalik / kunlik) ----------

@router.callback_query(F.data == "admgencode")
async def cb_gencode(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await call.message.edit_text("Kod qanday turdagi limit bersin?", reply_markup=gencode_type_kb())
    await call.answer()


@router.callback_query(F.data.startswith("admgencodetype:"))
async def cb_gencode_type(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    gtype = call.data.split(":", 1)[1]
    await state.set_state(GenCode.waiting_amount)
    await state.update_data(code_type=gtype)
    await call.message.answer("Kod qancha limit (nechta rasm) qo'shsin?", reply_markup=cancel_kb())
    await call.answer()


async def _finalize_code(message: Message, bot: Bot, gtype: str, amount: int, days: int | None):
    code = generate_code()
    store.data["codes"][code] = {
        "type": gtype,
        "amount": amount,
        "days": days,
        "used": False,
    }
    store.schedule_save(bot)
    if gtype == "daily":
        info = f"+{amount} limit, kuniga, {days} kun davomida amal qiladi."
    else:
        info = f"+{amount} limit, doimiy (bir martalik ishlatiladi)."
    await message.answer(f"✅ Kod yaratildi:\n\n<code>{code}</code>\n\n{info}")


@router.message(GenCode.waiting_amount)
async def gencode_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Raqam kiriting.")
    data = await state.get_data()
    if data.get("code_type") == "onetime":
        await state.clear()
        await _finalize_code(message, bot, "onetime", amount, None)
        return
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
    await _finalize_code(message, bot, "daily", data["amount"], days)


# ---------- Taqiqlangan so'zlar ----------

@router.callback_query(F.data == "admwords")
async def cb_words(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
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
async def addword(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    word = message.text.partition(" ")[2].strip()
    if not word:
        return await message.answer("Foydalanish: /addword [so'z]")
    store.data.setdefault("banned_words", [])
    if word not in store.data["banned_words"]:
        store.data["banned_words"].append(word)
        store.schedule_save(bot)
    await message.answer(f"✅ Qo'shildi: {word}")


@router.message(Command("delword"))
async def delword(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    word = message.text.partition(" ")[2].strip()
    if word in store.data.get("banned_words", []):
        store.data["banned_words"].remove(word)
        store.schedule_save(bot)
        await message.answer(f"✅ O'chirildi: {word}")
    else:
        await message.answer("Bu so'z qo'shimcha ro'yxatda topilmadi (asosiy ro'yxatdagi so'zlar o'chirilmaydi).")


# ---------- Custom (premium) emoji ----------

@router.callback_query(F.data == "admemoji")
async def cb_emoji(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    emojis = store.data.get("custom_emojis", {})
    text = "😀 Custom emoji ro'yxati:\n" + (
        "\n".join(f"- {k}: {v}" for k, v in emojis.items()) or "—"
    )
    text += "\n\nQo'shish: /addemoji [kalit] [custom_emoji_id]\nO'chirish: /delemoji [kalit]"
    await call.message.answer(text)
    await call.answer()


@router.message(Command("addemoji"))
async def addemoji(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return await message.answer("Foydalanish: /addemoji [kalit] [custom_emoji_id]")
    key, emoji_id = parts[1], parts[2]
    store.data.setdefault("custom_emojis", {})[key] = emoji_id
    store.schedule_save(bot)
    try:
        await message.answer(
            "🙂",
            entities=[MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id=emoji_id)],
        )
    except Exception:
        pass
    await message.answer(f"✅ Qo'shildi: {key} -> {emoji_id}")


@router.message(Command("delemoji"))
async def delemoji(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    key = message.text.partition(" ")[2].strip()
    if key in store.data.get("custom_emojis", {}):
        del store.data["custom_emojis"][key]
        store.schedule_save(bot)
        await message.answer(f"✅ O'chirildi: {key}")
    else:
        await message.answer("Topilmadi.")


# ---------- Istalgan (bot yuborgan) xabarni premium emoji bilan tahrirlash ----------

@router.callback_query(F.data == "admeditemoji")
async def cb_edit_emoji(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer()
    emojis = store.data.get("custom_emojis", {})
    keys = ", ".join(f"{{{k}}}" for k in emojis) or "— (avval /addemoji orqali qo'shing)"
    await state.set_state(EditMessageEmoji.waiting_target)
    await call.message.answer(
        "⚠️ Bot FAQAT o'zi yuborgan xabarlarni tahrirlay oladi (Telegram cheklovi).\n\n"
        "Tahrirlanadigan xabarni <code>chat_id:message_id</code> ko'rinishida yuboring "
        "(masalan: <code>-1001234567890:456</code>).",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(EditMessageEmoji.waiting_target)
async def edit_emoji_target(message: Message, state: FSMContext):
    try:
        chat_id_s, msg_id_s = message.text.strip().split(":")
        chat_id, msg_id = int(chat_id_s), int(msg_id_s)
    except Exception:
        return await message.answer("❌ Format: chat_id:message_id")
    await state.update_data(chat_id=chat_id, message_id=msg_id)
    emojis = store.data.get("custom_emojis", {})
    keys = ", ".join(f"{{{k}}}" for k in emojis) or "—"
    await state.set_state(EditMessageEmoji.waiting_text)
    await message.answer(
        f"Yangi matnni yuboring. Emoji qo'yish uchun kalitlarni {{qavs}} ichida yozing.\n"
        f"Mavjud kalitlar: {keys}"
    )


@router.message(EditMessageEmoji.waiting_text)
async def edit_emoji_text(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    text, entities = build_emoji_entities(message.text, store.data.get("custom_emojis", {}))
    try:
        await bot.edit_message_text(
            chat_id=data["chat_id"], message_id=data["message_id"],
            text=text, entities=entities or None,
        )
        await message.answer("✅ Xabar tahrirlandi.")
    except Exception as e:
        await message.answer(f"❌ Tahrirlab bo'lmadi (bot shu xabarni yuborgan bo'lishi kerak): {e}")


# ---------- Premium reaksiya adminlari ----------

@router.callback_query(F.data == "admreactions")
async def cb_reactions(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
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
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.partition(" ")[2].strip())
    except ValueError:
        return await message.answer("Foydalanish: /addreactionadmin [user_id]")
    lst = store.data.setdefault("reaction_admins", [])
    if uid not in lst:
        lst.append(uid)
        store.schedule_save(bot)
    await message.answer(f"✅ Qo'shildi: {uid}")


@router.message(Command("delreactionadmin"))
async def del_reaction_admin(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.partition(" ")[2].strip())
    except ValueError:
        return await message.answer("Foydalanish: /delreactionadmin [user_id]")
    lst = store.data.setdefault("reaction_admins", [])
    if uid in lst:
        lst.remove(uid)
        store.schedule_save(bot)
        await message.answer(f"✅ O'chirildi: {uid}")
    else:
        await message.answer("Topilmadi.")


@router.message(Command("setreactionemoji"))
async def set_reaction_emoji(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    emoji_id = message.text.partition(" ")[2].strip()
    if not emoji_id:
        return await message.answer("Foydalanish: /setreactionemoji [custom_emoji_id]")
    store.data["reaction_emoji_id"] = emoji_id
    store.schedule_save(bot)
    await message.answer("✅ Reaksiya emoji o'rnatildi.")


# ---------- Adminlarni boshqarish (faqat superadmin) ----------

@router.callback_query(F.data == "admmanageadmins")
async def cb_manage_admins(call: CallbackQuery):
    if not is_superadmin(call.from_user.id):
        return await call.answer("Faqat superadmin uchun.", show_alert=True)
    admins = store.data.get("admins", [])
    text = "🛠 Adminlar ro'yxati (bosilsa o'chiriladi):\n\nYangi qo'shish: /addadmin [user_id]"
    await call.message.edit_text(text, reply_markup=manage_admins_kb(admins))
    await call.answer()


@router.callback_query(F.data.startswith("admdeladmin:"))
async def cb_del_admin_btn(call: CallbackQuery, bot: Bot):
    if not is_superadmin(call.from_user.id):
        return await call.answer("Faqat superadmin uchun.", show_alert=True)
    uid = int(call.data.split(":", 1)[1])
    lst = store.data.setdefault("admins", [])
    if uid in lst:
        lst.remove(uid)
        store.schedule_save(bot)
    await cb_manage_admins(call)


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
        store.schedule_save(bot)
    await message.answer(f"✅ Admin qo'shildi: {uid}. U endi superadmin qila oladigan hamma ishni qila oladi.")


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
        store.schedule_save(bot)
        await message.answer(f"✅ Admin o'chirildi: {uid}")
    else:
        await message.answer("Topilmadi.")


# ---------- Admin/superadmin DB ga rasm tashlaydi -> keshlanadi ----------

@router.message(F.photo)
async def cache_admin_photo(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    from config import DB_GROUP_ID
    photo = message.photo[-1]
    store.add_image_cache(photo.file_id, message.from_user.id, message.caption)
    store.schedule_save(bot)
    try:
        await bot.send_photo(
            DB_GROUP_ID, photo.file_id,
            caption=f"🖼 Admin keshi\n👤 {message.from_user.full_name} [id: {message.from_user.id}]\n"
                    f"📝 {message.caption or '—'}",
        )
    except Exception as e:
        print(f"[cache] DB ga yuborishda xato: {e}")
    await message.answer("✅ Rasm keshga saqlandi va DB guruhiga yuborildi.")
