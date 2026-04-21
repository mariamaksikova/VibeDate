from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher

from app.config import load_settings
from app.db import create_pool
from app.handlers import common_router, dating_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    settings = load_settings()
    pool = await create_pool(settings.database_url)

    bot = Bot(token=settings.bot_token)

    dp = Dispatcher()
    dp.include_router(common_router)
    dp.include_router(dating_router)

    logger.info("Bot started")
    try:
        await dp.start_polling(bot, db_pool=pool)
    finally:
        await pool.close()
        await bot.session.close()
        logger.info("Bot stopped")


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run())


if __name__ == "__main__":
    main()
