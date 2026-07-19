import os
import secrets
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_GROUP_ID = int(os.getenv("DB_GROUP_ID", "0"))
SUPERADMIN_ID = int(os.getenv("SUPERADMIN_ID", "0"))

# ============================
# WEBHOOK sozlamalari (Render uchun)
# ============================
# Render "Web Service" har bir deploy'da RENDER_EXTERNAL_URL degan
# environment variable'ni O'ZI avtomatik beradi (masalan
# https://sening-servising.onrender.com) - qo'lda kiritish shart emas.
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", os.getenv("WEBHOOK_HOST", ""))
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Telegram har bir webhook so'roviga shu tokenni header'da qo'shib yuboradi -
# bu orqali so'rov chindan Telegramdan kelayotganini tekshiramiz.
# Render Environment Variables'ga o'zing tasodifiy uzun satr qo'yishing tavsiya
# qilinadi (masalan: openssl rand -hex 32); bo'lmasa har restart'da yangi
# tasodifiy qiymat generatsiya qilinadi (ishlayveradi, lekin beqaror).
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") or secrets.token_urlsafe(32)

# Render "$PORT" environment variable orqali qaysi portni tinglash kerakligini beradi
PORT = int(os.getenv("PORT", "10000"))

# Har bir userga sutkalik standart limit
DEFAULT_DAILY_LIMIT = 5

# Guruhga pin qilinadigan "database" fayl nomi (HTML - ko'rinishi chiroyli,
# ichida esa qayta tiklash uchun JSON embed qilingan)
STATE_FILENAME = "bot_state.html"

# Har bir o'zgarishdan keyin nechchi soniyadan so'ng DB faylga yozilsin
# (bir nechta o'zgarish ketma-ket kelsa, bittasiga birlashtirib saqlaydi)
SAVE_DEBOUNCE_SECONDS = 2

# Taqiqlangan so'zlar (butun so'z sifatida tekshiriladi, substring emas).
# "am" kabi juda qisqa/keng tarqalgan so'zlar yolg'on signal berishi mumkin -
# xohlasang keyinchalik bu ro'yxatni kengaytirish/torayтirish kerak bo'ladi.
BANNED_WORDS = [
    "18+",
    "porn",
    "sex",
    "xxx",
    "am",
    "jinsiy aloqa",
    "jinsiy azo",
    "yalang'och",
    "yalangoch",
    "kiyimsiz",
]

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
