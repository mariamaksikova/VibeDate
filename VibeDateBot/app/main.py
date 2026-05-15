from __future__ import annotations

import asyncio
import logging
import sys

import structlog
from aiogram import Bot, Dispatcher
from redis.asyncio import Redis

from app.config import load_settings
from app.db import create_pool
from app.events_rabbitmq import shutdown_publisher
from app.handlers import common_router, dating_router
from app.metrics import start_metrics_http_server_if_configured

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = structlog.get_logger(__name__)


async def run() -> None:
    settings = load_settings()
    pool = await create_pool(settings.database_url)

    redis: Redis | None = None
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        await redis.ping()
        logger.info("redis_ok", url=settings.redis_url.split("@")[-1])
    except Exception as exc:
        logger.warning("redis_unavailable", error=str(exc))
        redis = None

    start_metrics_http_server_if_configured()

    bot = Bot(token=settings.bot_token)

    dp = Dispatcher()
    dp.include_router(common_router)
    dp.include_router(dating_router)

    logger.info("bot_started")
    try:
        await dp.start_polling(bot, db_pool=pool, redis=redis)
    finally:
        if redis is not None:
            await redis.aclose()
        await pool.close()
        await bot.session.close()
        shutdown_publisher()
        logger.info("bot_stopped")


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run())


if __name__ == "__main__":
    main()
