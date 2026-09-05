import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_IDS
from database import init_db, get_accounts
import userbot as ub
import dialogue
from handlers_main import router as main_router
from handlers_accounts import router as accounts_router
from handlers_profile import router as profile_router
from handlers_dialogue import router as dialogue_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    logger.info("DB ready")

    bot = Bot(token=BOT_TOKEN)
    dialogue.init(bot, ADMIN_IDS)
    ub.set_incoming_handler(dialogue.handle_incoming_message)

    # One-time convenience: if no accounts are saved yet but env vars are set
    # (e.g. first deploy), adopt them as the first account.
    if not await get_accounts():
        session_string = os.getenv("SESSION_STRING", "").strip()
        api_id = int(os.getenv("API_ID", "0"))
        api_hash = os.getenv("API_HASH", "").strip()
        if session_string and api_id and api_hash:
            result = await ub.connect_account("Основной", api_id, api_hash, session_string)
            logger.info("Bootstrapped account from env vars: %s", result.get("ok", result))

    started = await ub.start_saved_accounts()
    logger.info("Reconnected %d saved account(s)", started)

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(accounts_router)
    dp.include_router(profile_router)
    dp.include_router(dialogue_router)
    dp.include_router(main_router)

    logger.info("Polling started")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
