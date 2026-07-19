from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, BufferedInputFile, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import DB_GROUP_ID, SUPERADMIN_ID, TARIFF_LABELS, TARIFF_ORDER
from state import store, UNLIMITED
from moderation import contains_banned
from pollinations import generate_image
from codes import redeem
from keyboards import main_menu, tariff_purchase_kb
from states import RequestTariff, UserContact
from queue_worker import gen_queue

router = Router()

_bot_username_cache = {"value": None}


async def _get_bot_username(bot: Bot) -> str:
    if not _bot_username_cache["value"]:
        me = await bot.get_me()
        _bot_username_cache["value"] = me.username
    return _bot_username_cache["value"]


def _left_text(user_id: int) -> str:
    left = store.remaining_limit(user_id)
    return "♾ Cheksiz" if left >= UNLIMITED else str(left)


async def _generate_job(message: Message, bot: Bot, prompt: str, user_id: int, status: Message):
    try:
        await status.edit_text("⏳ Rasm tayyorlanmoqda, biroz kuting...")
    except Exception:
        pass

    try:
        img_bytes = await generate_image(prompt)
    except Exception as e:
        print(f"[generate] Pollinations xatosi (prompt={prompt!r}): {type(e).__name__}: {e}")
        try:
            await status.edit_text("❌ Xatolik yuz berdi. Birozdan so'ng qaytadan urinib ko'ring.")
        except Exception:
            pass
        return

    store.consume_limit(user_id, 1)
    store.log_prompt(user_id, prompt, blocked=False)

    photo = BufferedInputFile(img_bytes, filename="result.png")
    sent_photo = await message.answer_photo(
        photo, caption=f"✅ Tayyor!\nQolgan limit: {_left_text(user_id)}"
    )
    try:
        await status.delete()
    except Exception:
        pass

    if sent_photo.photo:
        store.log_image(user_id, sent_photo.photo[-1].file_id, prompt)
    store.schedule_save(bot)

    try:
        await bot.send_photo(
            DB_GROUP_ID,
            BufferedInputFile(img_bytes, filename="log.png"),
            caption=(
                f"🖼 Yangi generatsiya\n"
                f"👤 {message.from_user.full_name} (@{message.from_user.username or '—'}) [id: {user_id}]\n"
                f"📝 Prompt: {prompt}"
            ),
        )
    except Exception as e:
        print(f"[log] guruhga yuborishda xato: {e}")


async def _do_generate(message: Message, bot: Bot, prompt: str):
    user = message.from_user
    u = store.get_user(user.id, user.username)

    if u.get("banned"):
        await message.answer("🚫 Siz botdan foydalanishdan taqiqlangansiz.")
        return

    remaining = store.remaining_limit(user.id)
    if remaining <= 0:
        await message.answer(
            "🚫 Sutkalik limitingiz tugagan.\n"
            "Ko'proq limit kerak bo'lsa \"💳 Tarif sotib olish\" tugmasidan foydalaning."
        )
        return

    banned = contains_banned(prompt, store.all_banned_words())
    if banned:
        store.consume_limit(user.id, 1)
        store.log_prompt(user.id, prompt, blocked=True)
        store.schedule_save(bot)
        await message.answer(
            "⛔️ So'rovingiz axloqiy qoidalarga zid so'z/ibora tutgani uchun rad etildi.\n"
            "Limitingizdan 1 ta ayirildi."
        )
        return

    # navbat: bir vaqtda ko'p kishi so'rasa ham hech kim xato olmaydi,
    # bittadan ketma-ket bajariladi
    position = gen_queue.peek_position()
    if position > 0:
        status = await message.answer(f"⏳ Navbatga qo'shildingiz. Sizdan oldin {position} ta so'rov bor.")
    else:
        status = await message.answer("⏳ Rasm tayyorlanmoqda, biroz kuting...")

    async def job():
        await _generate_job(message, bot, prompt, user.id, status)

    await gen_queue.enqueue(job)


@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot, state: FSMContext, command: CommandObject):
    await state.clear()
    is_new = str(message.from_user.id) not in store.data["users"]
    store.get_user(message.from_user.id, message.from_user.username)

    if is_new and command.args and command.args.startswith("ref"):
        try:
            referrer_id = int(command.args[3:])
            ok, upgraded = store.register_referral(referrer_id, message.from_user.id)
            if ok and upgraded:
                label = TARIFF_LABELS.get(upgraded, upgraded)
                try:
                    await bot.send_message(
                        referrer_id,
                        f"🎉 Tabriklaymiz! Siz yetarlicha referal keltirdingiz va avtomatik {label} tarifiga o'tkazildingiz!",
                    )
                except Exception:
                    pass
        except ValueError:
            pass

    store.schedule_save(bot)
    await message.answer(
        "👋 Xush kelibsiz!\n\n"
        "🎨 Rasm yaratish uchun: /generate [prompt] yoki pastdagi tugmadan foydalaning.\n"
        "Har kuni bepul limitingiz bor.",
        reply_markup=main_menu(store.is_admin_user(message.from_user.id)),
    )


@router.message(Command("generate"))
async def cmd_generate(message: Message, command: CommandObject, bot: Bot):
    if not command.args:
        await message.answer("Foydalanish: /generate [prompt]\nMasalan: /generate a cat astronaut in space")
        return
    await _do_generate(message, bot, command.args)


@router.message(F.text == "🎨 Rasm yaratish")
async def btn_generate(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Qanday rasm yaratay? Promptni yozib yuboring (masalan: sunset over mountains).")


@router.message(F.text == "📊 Limitim")
async def btn_limit(message: Message, state: FSMContext):
    await state.clear()
    u = store.get_user(message.from_user.id, message.from_user.username)
    tariff = TARIFF_LABELS.get(u.get("tariff", "free"), "Free")
    await message.answer(f"💳 Tarifingiz: {tariff}\n📊 Bugun {_left_text(message.from_user.id)} ta rasm yaratish imkoniyati qoldi.")


@router.message(F.text == "🔑 Kod kiritish")
async def btn_code(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("16 xonali kodni yuboring:")


@router.message(F.text == "🏆 Reyting")
async def btn_rating(message: Message, state: FSMContext):
    await state.clear()
    top = store.top_users(10)
    if not top:
        await message.answer("Hozircha reyting bo'sh — birinchi bo'lib rasm yarating! 🎨")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 Top 10 (eng ko'p rasm yaratganlar):\n"]
    for i, (uid, u) in enumerate(top):
        rank = medals[i] if i < 3 else f"{i + 1}."
        name = u.get("username") or f"id{uid}"
        lines.append(f"{rank} @{name} — {u.get('images_generated', 0)} ta rasm")
    await message.answer("\n".join(lines))


@router.message(F.text == "🔗 Referal havolam")
async def btn_referral(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    u = store.get_user(message.from_user.id, message.from_user.username)
    username = await _get_bot_username(bot)
    link = f"https://t.me/{username}?start=ref{message.from_user.id}"
    pro_req = store.data["tariffs"]["pro"]["ref_required"]
    plus_req = store.data["tariffs"]["plus"]["ref_required"]
    await message.answer(
        f"🔗 Sizning referal havolangiz:\n{link}\n\n"
        f"👥 Hozirgi referallaringiz: {u.get('ref_count', 0)} ta\n\n"
        f"{pro_req} ta referal → ⭐ Pro tarifi avtomatik beriladi\n"
        f"{plus_req} ta referal → 💎 Plus tarifi avtomatik beriladi"
    )


@router.message(F.text == "✉️ Adminga murojaat")
async def btn_admin_contact(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(UserContact.waiting_message)
    await message.answer("✍️ Adminga qanday xabar/muammo yozmoqchisiz?")


@router.message(UserContact.waiting_message)
async def admin_contact_message(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = message.from_user
    text = (
        f"📨 Yangi murojaat!\n"
        f"👤 {user.full_name} (@{user.username or '—'}) [id: {user.id}]\n"
        f"✍️ Xabar: {message.text}"
    )
    sent_to_any = False
    for admin_id in [SUPERADMIN_ID] + store.data.get("admins", []):
        try:
            await bot.send_message(admin_id, text)
            sent_to_any = True
        except Exception:
            pass
    if sent_to_any:
        await message.answer("✅ Murojaatingiz adminga yuborildi.")
    else:
        await message.answer("❌ Hozircha yuborib bo'lmadi, keyinroq urinib ko'ring.")


# ---------- Tarif sotib olish ----------

@router.message(F.text == "💳 Tarif sotib olish")
async def btn_tariff(message: Message, state: FSMContext):
    await state.clear()
    t = store.data["tariffs"]
    lines = ["💳 Mavjud tariflar:\n"]
    for name in TARIFF_ORDER:
        if name == "free":
            continue
        info = t[name]
        label = TARIFF_LABELS.get(name, name)
        lines.append(
            f"{label}: kuniga {info['daily_limit']} ta rasm — {info['price_stars']} ⭐/oy "
            f"yoki {info['ref_required']} ta referal"
        )
    lines.append("\nTanlang, admin bilan bog'lanamiz:")
    await message.answer("\n".join(lines), reply_markup=tariff_purchase_kb())


@router.callback_query(F.data.startswith("tariffreq:"))
async def cb_tariff_request(call: CallbackQuery, bot: Bot):
    tariff = call.data.split(":", 1)[1]
    label = TARIFF_LABELS.get(tariff, tariff)
    info = store.data["tariffs"].get(tariff, {})
    user = call.from_user
    text = (
        f"💳 Yangi tarif so'rovi!\n"
        f"👤 {user.full_name} (@{user.username or '—'}) [id: {user.id}]\n"
        f"🎫 So'ralgan tarif: {label} ({info.get('price_stars')} ⭐/oy yoki {info.get('ref_required')} referal)"
    )
    sent_to_any = False
    for admin_id in [SUPERADMIN_ID] + store.data.get("admins", []):
        try:
            await bot.send_message(admin_id, text)
            sent_to_any = True
        except Exception:
            pass
    if sent_to_any:
        await call.message.answer(f"✅ {label} tarifi uchun so'rovingiz adminga yuborildi. Tez orada bog'lanishadi.")
    else:
        await call.message.answer("❌ Hozircha yuborib bo'lmadi, keyinroq urinib ko'ring.")
    await call.answer()


@router.message(RequestTariff.waiting_message)
async def tariff_request(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = message.from_user
    text = (
        f"💳 Yangi murojaat (tarif)!\n"
        f"👤 {user.full_name} (@{user.username or '—'}) [id: {user.id}]\n"
        f"✍️ Xabar: {message.text}"
    )
    sent_to_any = False
    for admin_id in [SUPERADMIN_ID] + store.data.get("admins", []):
        try:
            await bot.send_message(admin_id, text)
            sent_to_any = True
        except Exception:
            pass
    if sent_to_any:
        await message.answer("✅ So'rovingiz adminga yuborildi. Tez orada javob berishadi.")
    else:
        await message.answer("❌ Hozircha yuborib bo'lmadi, keyinroq urinib ko'ring.")


# 16 xonali kod yoki oddiy matn -> avval kod sifatida tekshiramiz, aks holda prompt sifatida rasm yaratamiz
@router.message(F.text & ~F.text.startswith("/"))
async def free_text(message: Message, bot: Bot):
    text = message.text.strip()

    if len(text) == 16 and text.replace(" ", "").isalnum():
        ok, msg, entry = redeem(store.data, text, message.from_user.id)
        if ok:
            store.grant_tariff(message.from_user.id, entry["tariff"], entry.get("days"))
            store.schedule_save(bot)
        await message.answer(msg)
        return

    await _do_generate(message, bot, text)
