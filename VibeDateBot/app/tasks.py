from __future__ import annotations

import asyncio
import logging

from app.celery_app import celery_app
from app.config import load_settings
from app.db import create_pool
from app.services.profile import refresh_profile_rating

logger = logging.getLogger(__name__)


async def _recalculate_all_ratings_async() -> int:
    settings = load_settings()
    pool = await create_pool(settings.database_url)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM profiles ORDER BY id")
        count = 0
        for row in rows:
            await refresh_profile_rating(pool, int(row["id"]))
            count += 1
        logger.info("Celery: refreshed ratings for %s profiles", count)
        return count
    finally:
        await pool.close()


@celery_app.task(name="app.tasks.recalculate_all_ratings")
def recalculate_all_ratings() -> int:
    """Periodic full pass over profiles.ratings (этап 4: Celery + отдельная таблица ratings)."""
    return asyncio.run(_recalculate_all_ratings_async())
