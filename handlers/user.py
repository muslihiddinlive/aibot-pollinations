from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.context import FSMContext

from config import DB_GROUP_ID, SUPERADMIN_ID
from state import store
from moderation import contains_banned
from pollinations import generate_image
from codes import redeem
from keyboards import main_menu
from states import RequestTariff, UserContact

router = Router()


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
            "Ko'proq limit kerak bo'lsa, kod kiriting yoki \"💳 Tarif sotib olish\" tugmasi orqali murojaat qiling."
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

    status = await message.answer("⏳ Rasm tayyorlanmoqda, biroz kuting...")

    try:
        img_bytes = await generate_image(prompt)
    except Exception as e:
        print(f"[generate] Pollinations xatosi (prompt={prompt!r}): {type(e).__name__}: {e}")
        await status.edit_text("❌ Xatolik yuz berdi. Birozdan so'ng qaytadan urinib ko'ring.")
        return

    store.consume_limit(user.id, 1)
    store.log_prompt(user.id, prompt, blocked=False)

    photo = BufferedInputFile(img_bytes, filename="result.png")
    left = store.remaining_limit(user.id)
    left_text = "♾ Cheksiz" if left >= 10 ** 9 else str(left)
    sent_photo = await message.answer_photo(
        photo,
        caption=f"✅ Tayyor!\nQolgan limit: {left_text}",
    )
    await status.delete()

    # keyinchalik "yaratgan rasmlari" bo'limida ko'rsatish uchun file_id'ni saqlaymiz
    if sent_photo.photo:
        store.log_image(user.id, sent_photo.photo[-1].file_id, prompt)
    store.schedule_save(bot)

    # DB guruhiga log: user + prompt + rasm
    try:
        await bot.send_photo(
            DB_GROUP_ID,
            BufferedInputFile(img_bytes, filename="log.png"),
            caption=(
                f"🖼 Yangi generatsiya\n"
                f"👤 {user.full_name} (@{user.username or '—'}) [id: {user.id}]\n"
                f"📝 Prompt: {prompt}"
            ),
        )
    except Exception as e:
        print(f"[log] guruhga yuborishda xato: {e}")


@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    store.get_user(message.from_user.id, message.from_user.username)
    store.schedule_save(bot)
    await message.answer(
        "👋 Xush kelibsiz!\n\n"
        "🎨 Rasm yaratish uchun: /generate [prompt] yoki pastdagi tugmadan foydalaning.\n"
        f"Har kuni bepul limitingiz bor.",
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
    left = store.remaining_limit(message.from_user.id)
    left_text = "♾ Cheksiz" if left >= 10 ** 9 else str(left)
    await message.answer(f"📊 Sizda bugun {left_text} ta rasm yaratish imkoniyati qoldi.")


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


@router.message(F.text == "✉️ Adminga murojaat")
async def btn_admin_contact(message: Message, state: FSMContext):
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


@router.message(F.text == "💳 Tarif sotib olish")
async def btn_tariff(message: Message, state: FSMContext):
    await state.set_state(RequestTariff.waiting_message)
    await message.answer("Adminга nima yozmoqchisiz? (masalan: qancha limit kerakligini yozing)")


@router.message(RequestTariff.waiting_message)
async def tariff_request(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = message.from_user
    text = (
        f"💳 Yangi tarif so'rovi!\n"
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
            if entry.get("type") == "daily":
                store.grant_limit(message.from_user.id, entry["amount"], entry["days"])
            else:
                store.grant_permanent(message.from_user.id, entry["amount"])
            store.schedule_save(bot)
        await message.answer(msg)
        return

    await _do_generate(message, bot, text)
