import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_GROUP_ID = int(os.getenv("DB_GROUP_ID", "0"))
SUPERADMIN_ID = int(os.getenv("SUPERADMIN_ID", "0"))

# Har bir userga sutkalik standart limit
DEFAULT_DAILY_LIMIT = 5

# Guruhga pin qilinadigan "database" fayl nomi
STATE_FILENAME = "bot_state.json"

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
