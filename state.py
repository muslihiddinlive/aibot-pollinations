"""
"Database" qatlami.

Ishlash printsipi:
- Butun bot holati (userlar, tariflar, kodlar, taqiqlangan so'zlar, emoji ID'lar,
  adminlar, rasm keshi) bitta JSON obyekt sifatida RAMda saqlanadi (CACHE).
- Har bir o'zgarishdan SAVE_DEBOUNCE_SECONDS soniya o'tib (bir nechta o'zgarish
  ketma-ket kelsa - bittasiga birlashtirilib) shu JSON chiroyli HTML hisobot
  ichiga (jadval + embed JSON) o'raladi, `bot_state.html` fayli sifatida DB
  guruhiga yuboriladi va PIN qilinadi (DATABASE, doimiy saqlash).
- Bot qayta ishga tushganda guruhdagi pin qilingan xabardan HTML faylni o'qib,
  ichidagi JSON'ni ajratib olib cache'ni tiklaydi.

Limit tizimi endi TARIF asosida: har user "free"/"pro"/"plus"/"vip" tarifga ega,
har tarifning o'z kunlik limiti bor (store.data["tariffs"] ichida, superadmin
o'zgartira oladi). Superadmin/admin userga faqat TARIF beradi, raw limit emas.
"""

import asyncio
import html as html_lib
import json
import io
from datetime import date, timedelta
from aiogram import Bot
from aiogram.types import BufferedInputFile

from config import (
    DB_GROUP_ID, STATE_FILENAME, SUPERADMIN_ID, SAVE_DEBOUNCE_SECONDS,
    DEFAULT_TARIFFS, TARIFF_ORDER,
)

UNLIMITED = 10 ** 9  # superadmin/admin uchun "cheksiz" limit ko'rsatkichi

_DEFAULT_STATE = {
    "users": {},            # str(user_id) -> user dict
    "admins": [],           # superadmin belgilagan qo'shimcha adminlar
    "reaction_admins": [],  # kimlarning xabariga premium reaksiya bosiladi
    "reaction_emoji_id": None,  # premium reaksiya uchun custom emoji id
    "tariffs": DEFAULT_TARIFFS,  # superadmin o'zgartira oladigan tarif sozlamalari
    "codes": {},             # code -> {"tariff", "days", "used", "used_by"}
    "banned_words": [],      # config.BANNED_WORDS ustiga runtime qo'shimchalar
    "custom_emojis": {},     # key -> custom_emoji_id (xabarlarni emoji bilan bezash uchun)
    "image_cache": [],       # admin/superadmin DB ga tashlagan rasmlar: {file_id, by, at, caption}
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
        cache'ni tiklaydi. Eski formatlardan yangisiga o'tishda ma'lumot yo'qolib
        ketmasligi uchun moslashtirib olamiz."""
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
                    loaded = json.loads(raw)
                else:
                    start = raw.index(_JSON_START) + len(_JSON_START)
                    end = raw.index(_JSON_END, start)
                    loaded = json.loads(raw[start:end])

                for k, v in _DEFAULT_STATE.items():
                    loaded.setdefault(k, json.loads(json.dumps(v)))

                for u in loaded.get("users", {}).values():
                    u.setdefault("images_generated", 0)
                    u.setdefault("generated_images", [])
                    u.setdefault("tariff", "free")
                    u.setdefault("tariff_until", None)
                    u.setdefault("ref_count", 0)
                    u.setdefault("referred_by", None)
                    # eski "daily_limit"/"extra_limit" maydonlari endi ishlatilmaydi,
                    # lekin xatolik chiqmasligi uchun tegmasdan qoldiramiz.

                # eski raw-limit kodlarini tarif tizimiga moslashtiramiz
                for c in loaded.get("codes", {}).values():
                    if "tariff" not in c:
                        c["tariff"] = "pro"
                    c.setdefault("days", None)

                if pinned.document.file_name == "bot_state.json":
                    loaded["pinned_message_id"] = None
                else:
                    loaded["pinned_message_id"] = pinned.message_id
                self.data = loaded
        except Exception as e:
            print(f"[state] load xatosi (birinchi ishga tushirish bo'lishi mumkin): {e}")
        self._loaded = True

    def schedule_save(self, bot: Bot):
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
                f"<td>{esc(u.get('tariff', 'free'))}</td>"
                f"<td>{esc(u.get('tariff_until') or 'doimiy')}</td>"
                f"<td>{esc(u.get('ref_count', 0))}</td>"
                f"<td>{'🚫' if u.get('banned') else '—'}</td>"
                "</tr>"
            )
        users_table = "\n".join(user_rows) or "<tr><td colspan='8'>—</td></tr>"

        code_rows = []
        for code, c in d.get("codes", {}).items():
            code_rows.append(
                "<tr>"
                f"<td>{esc(code)}</td>"
                f"<td>{esc(c.get('tariff'))}</td>"
                f"<td>{esc(c.get('days') or 'doimiy')}</td>"
                f"<td>{'✅ ishlatilgan (' + esc(c.get('used_by')) + ')' if c.get('used') else '🟢 band emas'}</td>"
                "</tr>"
            )
        codes_table = "\n".join(code_rows) or "<tr><td colspan='4'>—</td></tr>"

        tariff_rows = []
        for name, t in d.get("tariffs", {}).items():
            tariff_rows.append(
                "<tr>"
                f"<td>{esc(name)}</td><td>{esc(t.get('daily_limit'))}</td>"
                f"<td>{esc(t.get('price_stars'))}</td><td>{esc(t.get('ref_required'))}</td>"
                f"<td>{esc(t.get('grantable_by'))}</td>"
                "</tr>"
            )
        tariffs_table = "\n".join(tariff_rows)

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

<h2>💳 Tariflar</h2>
<table><tr><th>Nomi</th><th>Kunlik limit</th><th>Narx (stars)</th><th>Referal talabi</th><th>Kim beradi</th></tr>
{tariffs_table}
</table>

<h2>👥 Userlar ({len(users)} ta)</h2>
<table><tr><th>ID</th><th>Username</th><th>Qo'shilgan</th><th>Rasmlar</th><th>Tarif</th><th>Muddat</th><th>Refs</th><th>Ban</th></tr>
{users_table}
</table>

<h2>🔑 Kodlar ({len(d.get('codes', {}))} ta)</h2>
<table><tr><th>Kod</th><th>Tarif</th><th>Kun</th><th>Holat</th></tr>
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
        return self.is_admin_user(user_id)

    # ---------- user helpers ----------

    def get_user(self, user_id: int, username: str | None = None) -> dict:
        uid = str(user_id)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {
                "id": user_id,
                "username": username,
                "first_seen": str(date.today()),
                "tariff": "free",
                "tariff_until": None,   # None = muddatsiz; aks holda "YYYY-MM-DD"
                "used_today": 0,
                "last_reset": str(date.today()),
                "banned": False,
                "prompts": [],
                "images_generated": 0,
                "generated_images": [],
                "ref_count": 0,
                "referred_by": None,
            }
        else:
            u = self.data["users"][uid]
            if username:
                u["username"] = username
            u.setdefault("images_generated", 0)
            u.setdefault("generated_images", [])
            u.setdefault("tariff", "free")
            u.setdefault("tariff_until", None)
            u.setdefault("ref_count", 0)
            u.setdefault("referred_by", None)
        return self.data["users"][uid]

    def _reset_if_new_day(self, user: dict):
        today = str(date.today())
        if user["last_reset"] != today:
            user["last_reset"] = today
            user["used_today"] = 0
        if user.get("tariff_until") and user["tariff_until"] < today:
            user["tariff"] = "free"
            user["tariff_until"] = None

    def tariff_daily_limit(self, tariff_name: str) -> int:
        t = self.data.get("tariffs", {}).get(tariff_name)
        if not t:
            t = DEFAULT_TARIFFS.get(tariff_name, DEFAULT_TARIFFS["free"])
        return t["daily_limit"]

    def remaining_limit(self, user_id: int) -> int:
        if self.is_unlimited(user_id):
            return UNLIMITED
        user = self.get_user(user_id)
        self._reset_if_new_day(user)
        daily = self.tariff_daily_limit(user.get("tariff", "free"))
        return max(0, daily - user["used_today"])

    def consume_limit(self, user_id: int, amount: int = 1):
        user = self.get_user(user_id)
        self._reset_if_new_day(user)
        user["used_today"] += amount

    def log_prompt(self, user_id: int, prompt: str, blocked: bool = False):
        user = self.get_user(user_id)
        user["prompts"].append({"prompt": prompt, "at": str(date.today()), "blocked": blocked})
        user["prompts"] = user["prompts"][-50:]

    def log_image(self, user_id: int, file_id: str, prompt: str):
        user = self.get_user(user_id)
        user["images_generated"] = user.get("images_generated", 0) + 1
        user.setdefault("generated_images", []).append(
            {"file_id": file_id, "prompt": prompt, "at": str(date.today())}
        )
        user["generated_images"] = user["generated_images"][-20:]

    def grant_tariff(self, user_id: int, tariff_name: str, days: int | None = None):
        """Superadmin/admin userga tarif beradi. days=None -> muddatsiz."""
        user = self.get_user(user_id)
        user["tariff"] = tariff_name
        user["tariff_until"] = str(date.today() + timedelta(days=days)) if days else None

    def set_banned(self, user_id: int, banned: bool):
        self.get_user(user_id)["banned"] = banned

    def all_banned_words(self):
        from config import BANNED_WORDS
        return list(set(BANNED_WORDS) | set(self.data.get("banned_words", [])))

    def top_users(self, n: int = 10) -> list[tuple[str, dict]]:
        users = self.data.get("users", {})
        ranked = sorted(users.items(), key=lambda kv: -kv[1].get("images_generated", 0))
        return [(uid, u) for uid, u in ranked if u.get("images_generated", 0) > 0][:n]

    # ---------- referal tizimi ----------

    def register_referral(self, referrer_id: int, new_user_id: int) -> tuple[bool, str | None]:
        """Yangi user birinchi marta referal havola orqali kirganda chaqiriladi.
        Qaytaradi: (hisoblandi_mi, agar avto-tarif berilgan bo'lsa yangi tarif nomi)."""
        if referrer_id == new_user_id:
            return False, None
        if str(referrer_id) not in self.data["users"]:
            return False, None
        new_user = self.get_user(new_user_id)
        if new_user.get("referred_by"):
            return False, None  # allaqachon boshqa referaldan kirgan

        new_user["referred_by"] = referrer_id
        referrer = self.get_user(referrer_id)
        referrer["ref_count"] = referrer.get("ref_count", 0) + 1

        upgraded_to = None
        current_idx = TARIFF_ORDER.index(referrer.get("tariff", "free")) if referrer.get("tariff", "free") in TARIFF_ORDER else 0
        for name in reversed(TARIFF_ORDER):
            req = self.data.get("tariffs", {}).get(name, {}).get("ref_required", 0)
            if req and referrer["ref_count"] >= req and TARIFF_ORDER.index(name) > current_idx:
                referrer["tariff"] = name
                referrer["tariff_until"] = None
                upgraded_to = name
                break
        return True, upgraded_to

    # ---------- rasm keshi ----------

    def add_image_cache(self, file_id: str, by: int, caption: str | None = None):
        self.data.setdefault("image_cache", []).append({
            "file_id": file_id, "by": by, "at": str(date.today()), "caption": caption or "",
        })
        self.data["image_cache"] = self.data["image_cache"][-500:]


store = Store()
