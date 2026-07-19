"""
"Database" qatlami.

Ishlash printsipi:
- Butun bot holati (userlar, limitlar, kodlar, taqiqlangan so'zlar, emoji ID'lar,
  adminlar, rasm keshi) bitta JSON obyekt sifatida RAMda saqlanadi (CACHE).
- Har bir o'zgarishdan SAVE_DEBOUNCE_SECONDS soniya o'tib (bir nechta o'zgarish
  ketma-ket kelsa - bittasiga birlashtirilib) shu JSON chiroyli HTML hisobot
  ichiga (jadval + embed JSON) o'raladi, `bot_state.html` fayli sifatida DB
  guruhiga yuboriladi va PIN qilinadi (DATABASE, doimiy saqlash).
- Bot qayta ishga tushganda guruhdagi pin qilingan xabardan HTML faylni o'qib,
  ichidagi JSON'ni ajratib olib cache'ni tiklaydi.
"""

import asyncio
import html as html_lib
import json
import io
from datetime import date, timedelta
from aiogram import Bot
from aiogram.types import BufferedInputFile

from config import DB_GROUP_ID, STATE_FILENAME, DEFAULT_DAILY_LIMIT, SUPERADMIN_ID, SAVE_DEBOUNCE_SECONDS

UNLIMITED = 10 ** 9  # superadmin/admin uchun "cheksiz" limit ko'rsatkichi

_DEFAULT_STATE = {
    "users": {},            # str(user_id) -> user dict
    "admins": [],           # superadmin belgilagan qo'shimcha adminlar
    "reaction_admins": [],  # kimlarning xabariga premium reaksiya bosiladi
    "reaction_emoji_id": None,  # premium reaksiya uchun custom emoji id
    "codes": {},            # code -> {"type", "amount", "days", "used", "used_by"}
    "banned_words": [],     # config.BANNED_WORDS ustiga runtime qo'shimchalar
    "custom_emojis": {},    # key -> custom_emoji_id (xabarlarni emoji bilan bezash uchun)
    "image_cache": [],      # admin/superadmin DB ga tashlagan rasmlar: {file_id, by, at, caption}
    "pinned_message_id": None,
}

_JSON_START = '<script type="application/json" id="state-json">'
_JSON_END = "</script>"


class Store:
    def __init__(self):
        self.data = json.loads(json.dumps(_DEFAULT_STATE))  # deep copy
        self._loaded = False
        self._save_task: asyncio.Task | None = None

    # ---------- persistence ----------

    async def load(self, bot: Bot):
        """Guruhdagi pin qilingan bot_state.html (yoki eski bot_state.json) faylini o'qib,
        cache'ni tiklaydi. Eski JSON formatidan yangi HTML formatiga o'tishda ma'lumot
        yo'qolib ketmasligi uchun ikkalasini ham qo'llab-quvvatlaymiz."""
        try:
            chat = await bot.get_chat(DB_GROUP_ID)
            pinned = chat.pinned_message
            if pinned and pinned.document and pinned.document.file_name in (STATE_FILENAME, "bot_state.json"):
                file = await bot.get_file(pinned.document.file_id)
                buf = io.BytesIO()
                await bot.download_file(file.file_path, destination=buf)
                buf.seek(0)
                raw = buf.read().decode("utf-8")

                if pinned.document.file_name == "bot_state.json":
                    # eski (JSON) format - to'g'ridan-to'g'ri o'qiymiz
                    loaded = json.loads(raw)
                else:
                    start = raw.index(_JSON_START) + len(_JSON_START)
                    end = raw.index(_JSON_END, start)
                    loaded = json.loads(raw[start:end])

                # yangi versiyada qo'shilgan kalitlar bo'lsa, defaultlar bilan to'ldiramiz
                for k, v in _DEFAULT_STATE.items():
                    loaded.setdefault(k, json.loads(json.dumps(v)))
                # eski userlarga yangi maydonlarni qo'shib qo'yamiz
                for u in loaded.get("users", {}).values():
                    u.setdefault("images_generated", 0)
                    u.setdefault("generated_images", [])
                # eski kod formatida "limit_add"/"days" bo'lgan, yangisida "amount"/"type" kerak
                for c in loaded.get("codes", {}).values():
                    if "amount" not in c and "limit_add" in c:
                        c["amount"] = c.pop("limit_add")
                    c.setdefault("type", "daily")

                # eski JSON fayl bo'lsa, keyingi saqlashda yangi HTML fayl sifatida
                # QAYTA yuborilishi kerak (eski pin o'chirilib, yangisi yaratiladi)
                if pinned.document.file_name == "bot_state.json":
                    loaded["pinned_message_id"] = None
                else:
                    loaded["pinned_message_id"] = pinned.message_id
                self.data = loaded
        except Exception as e:
            print(f"[state] load xatosi (birinchi ishga tushirish bo'lishi mumkin): {e}")
        self._loaded = True

    def schedule_save(self, bot: Bot):
        """SAVE_DEBOUNCE_SECONDS soniyadan keyin saqlaydi; shu oraliqda yana chaqirilsa,
        eskisi bekor qilinib qayta hisoblanadi (ketma-ket o'zgarishlar bittaga birlashadi)."""
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
        self._save_task = asyncio.create_task(self._debounced_save(bot))

    async def _debounced_save(self, bot: Bot):
        try:
            await asyncio.sleep(SAVE_DEBOUNCE_SECONDS)
        except asyncio.CancelledError:
            return
        try:
            await self.save(bot)
        except Exception as e:
            print(f"[state] debounced save xatosi: {e}")

    async def save(self, bot: Bot):
        """Cache'ni HTML hisobot qilib guruhga yuboradi/yangilaydi va pin qiladi (darhol, kutmasdan)."""
        payload = self._build_html()
        file = BufferedInputFile(payload, filename=STATE_FILENAME)

        msg_id = self.data.get("pinned_message_id")
        try:
            if msg_id:
                from aiogram.types import InputMediaDocument
                await bot.edit_message_media(
                    chat_id=DB_GROUP_ID,
                    message_id=msg_id,
                    media=InputMediaDocument(media=file, caption="🗄 bot_state.html (avto-yangilanadi)"),
                )
            else:
                raise ValueError("pinned_message_id yo'q")
        except Exception:
            # birinchi marta yoki eski xabar topilmadi -> yangi yuboramiz va pin qilamiz
            sent = await bot.send_document(
                DB_GROUP_ID, file, caption="🗄 bot_state.html (avto-yangilanadi)"
            )
            self.data["pinned_message_id"] = sent.message_id
            try:
                await bot.pin_chat_message(DB_GROUP_ID, sent.message_id, disable_notification=True)
            except Exception as e:
                print(f"[state] pin qilishda xato: {e}")
            payload = self._build_html()
            try:
                from aiogram.types import InputMediaDocument
                await bot.edit_message_media(
                    chat_id=DB_GROUP_ID,
                    message_id=sent.message_id,
                    media=InputMediaDocument(
                        media=BufferedInputFile(payload, filename=STATE_FILENAME),
                        caption="🗄 bot_state.html (avto-yangilanadi)",
                    ),
                )
            except Exception as e:
                print(f"[state] ikkinchi yozishda xato: {e}")

    def _build_html(self) -> bytes:
        d = self.data
        users = d.get("users", {})

        def esc(v):
            return html_lib.escape(str(v)) if v is not None else "—"

        user_rows = []
        for uid, u in sorted(users.items(), key=lambda kv: -kv[1].get("images_generated", 0)):
            tag = " ⭐" if int(uid) in ({SUPERADMIN_ID} | set(d.get("admins", []))) else ""
            user_rows.append(
                "<tr>"
                f"<td>{esc(uid)}{tag}</td>"
                f"<td>{esc(u.get('username') or '—')}</td>"
                f"<td>{esc(u.get('first_seen', '—'))}</td>"
                f"<td>{esc(u.get('images_generated', 0))}</td>"
                f"<td>{esc(u.get('daily_limit', 0))}</td>"
                f"<td>{esc(u.get('extra_limit', 0))}</td>"
                f"<td>{'🚫' if u.get('banned') else '—'}</td>"
                "</tr>"
            )
        users_table = "\n".join(user_rows) or "<tr><td colspan='7'>—</td></tr>"

        code_rows = []
        for code, c in d.get("codes", {}).items():
            code_rows.append(
                "<tr>"
                f"<td>{esc(code)}</td>"
                f"<td>{esc(c.get('type', 'onetime'))}</td>"
                f"<td>{esc(c.get('amount'))}</td>"
                f"<td>{esc(c.get('days') or '—')}</td>"
                f"<td>{'✅ ishlatilgan (' + esc(c.get('used_by')) + ')' if c.get('used') else '🟢 band emas'}</td>"
                "</tr>"
            )
        codes_table = "\n".join(code_rows) or "<tr><td colspan='5'>—</td></tr>"

        admins = d.get("admins", [])
        admin_rows = "".join(f"<li>{esc(a)}</li>" for a in admins) or "<li>—</li>"

        cache = d.get("image_cache", [])

        html_out = f"""<!DOCTYPE html>
<html lang="uz"><head><meta charset="utf-8"><title>Bot Database</title>
<style>
body{{font-family:Arial,Helvetica,sans-serif;background:#0f1115;color:#e6e6e6;padding:24px}}
h1{{color:#7dd3fc}} h2{{color:#7dd3fc;margin-top:36px}}
table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #2c2f36;padding:6px 10px;font-size:13px;text-align:left}}
th{{background:#1b1e25}}
tr:nth-child(even){{background:#151821}}
.meta{{color:#9aa4b2;font-size:13px}}
</style></head><body>
<h1>🗄 Bot Database</h1>
<p class="meta">Superadmin: {esc(SUPERADMIN_ID)} | Yangilangan: {esc(date.today())}</p>

<h2>👥 Userlar ({len(users)} ta)</h2>
<table><tr><th>ID</th><th>Username</th><th>Qo'shilgan</th><th>Rasmlar</th><th>Kunlik</th><th>Qo'shimcha</th><th>Ban</th></tr>
{users_table}
</table>

<h2>🔑 Kodlar ({len(d.get('codes', {}))} ta)</h2>
<table><tr><th>Kod</th><th>Turi</th><th>Miqdor</th><th>Kun</th><th>Holat</th></tr>
{codes_table}
</table>

<h2>🛠 Adminlar</h2>
<ul>{admin_rows}</ul>

<h2>🖼 Rasm keshi ({len(cache)} ta)</h2>
<p class="meta">Adminlar tomonidan DB ga qo'lda tashlangan rasmlar soni.</p>

<script type="application/json" id="state-json">
{json.dumps(d, ensure_ascii=False)}
</script>
</body></html>"""
        return html_out.encode("utf-8")

    # ---------- ruxsatlar ----------

    def is_admin_user(self, user_id: int) -> bool:
        return user_id == SUPERADMIN_ID or user_id in self.data.get("admins", [])

    def is_unlimited(self, user_id: int) -> bool:
        # superadmin va u tayinlagan adminlar - cheksiz limit
        return self.is_admin_user(user_id)

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
                "prompts": [],           # so'nggi promptlar log (qisqa tarix)
                "images_generated": 0,   # jami yaratilgan rasmlar soni
                "generated_images": [],  # so'nggi yaratilgan rasmlar (file_id + prompt)
            }
        else:
            if username:
                self.data["users"][uid]["username"] = username
            self.data["users"][uid].setdefault("images_generated", 0)
            self.data["users"][uid].setdefault("generated_images", [])
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
        if self.is_unlimited(user_id):
            return UNLIMITED
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

    def log_image(self, user_id: int, file_id: str, prompt: str):
        user = self.get_user(user_id)
        user["images_generated"] = user.get("images_generated", 0) + 1
        user.setdefault("generated_images", []).append({
            "file_id": file_id,
            "prompt": prompt,
            "at": str(date.today()),
        })
        user["generated_images"] = user["generated_images"][-20:]

    def grant_limit(self, user_id: int, amount: int, days: int):
        """Muddatli (kunlik) bonus limit - `days` kun davomida har kuni +amount beriladi."""
        user = self.get_user(user_id)
        until = date.today() + timedelta(days=days)
        user["extra_limit"] = user.get("extra_limit", 0) + amount
        user["extra_limit_until"] = str(until)

    def grant_permanent(self, user_id: int, amount: int):
        """Bir martalik - foydalanuvchining doimiy kunlik limitiga qo'shib qo'yiladi (muddatsiz)."""
        user = self.get_user(user_id)
        user["daily_limit"] = user.get("daily_limit", DEFAULT_DAILY_LIMIT) + amount

    def set_banned(self, user_id: int, banned: bool):
        user = self.get_user(user_id)
        user["banned"] = banned

    def all_banned_words(self):
        from config import BANNED_WORDS
        return list(set(BANNED_WORDS) | set(self.data.get("banned_words", [])))

    def top_users(self, n: int = 10) -> list[tuple[str, dict]]:
        users = self.data.get("users", {})
        ranked = sorted(users.items(), key=lambda kv: -kv[1].get("images_generated", 0))
        return [(uid, u) for uid, u in ranked if u.get("images_generated", 0) > 0][:n]

    # ---------- rasm keshi ----------

    def add_image_cache(self, file_id: str, by: int, caption: str | None = None):
        self.data.setdefault("image_cache", []).append({
            "file_id": file_id,
            "by": by,
            "at": str(date.today()),
            "caption": caption or "",
        })
        # cheksiz o'smasin
        self.data["image_cache"] = self.data["image_cache"][-500:]


store = Store()
