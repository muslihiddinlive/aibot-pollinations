"""
"Database" qatlami.

Ishlash printsipi:
- Butun bot holati (userlar, limitlar, kodlar, taqiqlangan so'zlar, emoji ID'lar,
  adminlar) bitta JSON obyekt sifatida RAMda saqlanadi (CACHE).
- Har bir o'zgarishdan keyin shu JSON `bot_state.json` fayli sifatida
  DB guruhiga yuboriladi va PIN qilinadi (DATABASE, doimiy saqlash).
- Bot qayta ishga tushganda guruhdagi pin qilingan xabardan faylni o'qib,
  cache'ni tiklaydi.
"""

import json
import io
from datetime import date
from aiogram import Bot
from aiogram.types import BufferedInputFile

from config import DB_GROUP_ID, STATE_FILENAME, DEFAULT_DAILY_LIMIT

_DEFAULT_STATE = {
    "users": {},            # str(user_id) -> user dict
    "admins": [],           # superadmin belgilagan qo'shimcha adminlar
    "reaction_admins": [],  # kimlarning xabariga premium reaksiya bosiladi
    "reaction_emoji_id": None,  # premium reaksiya uchun custom emoji id
    "codes": {},            # code -> {"limit_add", "days", "used"}
    "banned_words": [],     # config.BANNED_WORDS ustiga runtime qo'shimchalar
    "custom_emojis": {},    # key -> custom_emoji_id (start xabari va h.k. uchun)
    "pinned_message_id": None,
}


class Store:
    def __init__(self):
        self.data = json.loads(json.dumps(_DEFAULT_STATE))  # deep copy
        self._loaded = False

    # ---------- persistence ----------

    async def load(self, bot: Bot):
        """Guruhdagi pin qilingan bot_state.json faylini o'qib cache'ni tiklaydi."""
        try:
            chat = await bot.get_chat(DB_GROUP_ID)
            pinned = chat.pinned_message
            if pinned and pinned.document and pinned.document.file_name == STATE_FILENAME:
                file = await bot.get_file(pinned.document.file_id)
                buf = io.BytesIO()
                await bot.download_file(file.file_path, destination=buf)
                buf.seek(0)
                loaded = json.loads(buf.read().decode("utf-8"))
                # yangi versiyada qo'shilgan kalitlar bo'lsa, defaultlar bilan to'ldiramiz
                for k, v in _DEFAULT_STATE.items():
                    loaded.setdefault(k, v)
                loaded["pinned_message_id"] = pinned.message_id
                self.data = loaded
        except Exception as e:
            print(f"[state] load xatosi (birinchi ishga tushirish bo'lishi mumkin): {e}")
        self._loaded = True

    async def save(self, bot: Bot):
        """Cache'ni JSON qilib guruhga yuboradi/yangilaydi va pin qiladi."""
        payload = json.dumps(self.data, ensure_ascii=False, indent=2).encode("utf-8")
        file = BufferedInputFile(payload, filename=STATE_FILENAME)

        msg_id = self.data.get("pinned_message_id")
        try:
            if msg_id:
                from aiogram.types import InputMediaDocument
                await bot.edit_message_media(
                    chat_id=DB_GROUP_ID,
                    message_id=msg_id,
                    media=InputMediaDocument(media=file, caption="🗄 bot_state.json (avto-yangilanadi)"),
                )
            else:
                raise ValueError("pinned_message_id yo'q")
        except Exception:
            # birinchi marta yoki eski xabar topilmadi -> yangi yuboramiz va pin qilamiz
            sent = await bot.send_document(
                DB_GROUP_ID, file, caption="🗄 bot_state.json (avto-yangilanadi)"
            )
            self.data["pinned_message_id"] = sent.message_id
            try:
                await bot.pin_chat_message(DB_GROUP_ID, sent.message_id, disable_notification=True)
            except Exception as e:
                print(f"[state] pin qilishda xato: {e}")
            # o'zgargan pinned_message_id ni ham darhol faylga yozib qo'yamiz
            payload = json.dumps(self.data, ensure_ascii=False, indent=2).encode("utf-8")
            try:
                await bot.edit_message_media(
                    chat_id=DB_GROUP_ID,
                    message_id=sent.message_id,
                    media=__import__("aiogram").types.InputMediaDocument(
                        media=BufferedInputFile(payload, filename=STATE_FILENAME),
                        caption="🗄 bot_state.json (avto-yangilanadi)",
                    ),
                )
            except Exception as e:
                print(f"[state] ikkinchi yozishda xato: {e}")

    # ---------- user helpers ----------

    def get_user(self, user_id: int, username: str | None = None) -> dict:
        uid = str(user_id)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {
                "id": user_id,
                "username": username,
                "first_seen": str(date.today()),
                "daily_limit": DEFAULT_DAILY_LIMIT,
                "used_today": 0,
                "last_reset": str(date.today()),
                "extra_limit": 0,
                "extra_limit_until": None,
                "banned": False,
                "prompts": [],  # so'nggi promptlar log (qisqa tarix)
            }
        else:
            if username:
                self.data["users"][uid]["username"] = username
        return self.data["users"][uid]

    def _reset_if_new_day(self, user: dict):
        today = str(date.today())
        if user["last_reset"] != today:
            user["last_reset"] = today
            user["used_today"] = 0
            # extra_limit muddati o'tgan bo'lsa, tozalaymiz
            if user.get("extra_limit_until") and user["extra_limit_until"] < today:
                user["extra_limit"] = 0
                user["extra_limit_until"] = None

    def remaining_limit(self, user_id: int) -> int:
        user = self.get_user(user_id)
        self._reset_if_new_day(user)
        total = user["daily_limit"] + user.get("extra_limit", 0)
        return max(0, total - user["used_today"])

    def consume_limit(self, user_id: int, amount: int = 1):
        user = self.get_user(user_id)
        self._reset_if_new_day(user)
        user["used_today"] += amount

    def log_prompt(self, user_id: int, prompt: str, blocked: bool = False):
        user = self.get_user(user_id)
        user["prompts"].append({
            "prompt": prompt,
            "at": str(date.today()),
            "blocked": blocked,
        })
        # faqat oxirgi 50 tasini saqlaymiz, fayl shishib ketmasin
        user["prompts"] = user["prompts"][-50:]

    def grant_limit(self, user_id: int, amount: int, days: int):
        user = self.get_user(user_id)
        from datetime import timedelta
        until = date.today() + timedelta(days=days)
        user["extra_limit"] = user.get("extra_limit", 0) + amount
        user["extra_limit_until"] = str(until)

    def all_banned_words(self):
        from config import BANNED_WORDS
        return list(set(BANNED_WORDS) | set(self.data.get("banned_words", [])))


store = Store()
