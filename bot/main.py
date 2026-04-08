from __future__ import annotations

import asyncio
import logging
import sys

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

from bot.config import load_settings
from bot.db import create_pool
from bot.handlers import help_cmd, start

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


def main() -> None:
    settings = load_settings()

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=10.0,
        proxy=settings.telegram_http_proxy,
    )

    async def post_init(app: Application) -> None:
        try:
            app.bot_data["db_pool"] = await create_pool(settings.database_url)
        except Exception:
            log.exception(
                "Не удалось подключиться к PostgreSQL. Проверьте DATABASE_URL, "
                "что Postgres запущен и выполнен скрипт vibedatebd.sql"
            )
            raise
        log.info("Database pool ready")

    async def post_shutdown(app: Application) -> None:
        pool = app.bot_data.get("db_pool")
        if pool is not None:
            await pool.close()
            log.info("Database pool closed")

    application = (
        Application.builder()
        .token(settings.bot_token)
        .request(request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))

    async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.exception("Unhandled error: %s", context.error)

    application.add_error_handler(on_error)

    log.info("Bot polling started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()
