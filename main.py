import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from state import store
from handlers import admin, user, reactions


async def main():
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Guruhdagi pin qilingan bot_state.json dan holatni tiklaymiz
    await store.load(bot)

    # TARTIB MUHIM:
    # 1) admin - komandalar va FSM holatlari (masalan broadcast matni kutish)
    # 2) user  - /generate, oddiy matn (prompt sifatida)
    # 3) reactions - faqat guruh xabarlari, eng oxirida, hech narsani "yutmasin"
    dp.include_router(admin.router)
    dp.include_router(user.router)
    dp.include_router(reactions.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
