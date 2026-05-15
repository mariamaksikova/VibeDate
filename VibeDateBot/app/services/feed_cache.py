from __future__ import annotations

import logging

import asyncpg
from redis.asyncio import Redis

from app.db import get_candidate_for_viewer, get_next_candidate_ids

logger = logging.getLogger(__name__)

FEED_QUEUE_SIZE = 10
FEED_KEY_PREFIX = "vibedate:feed:"


def _feed_key(viewer_tg_id: int) -> str:
    return f"{FEED_KEY_PREFIX}{viewer_tg_id}"


async def _queue_ids(redis: Redis, viewer_tg_id: int) -> list[int]:
    key = _feed_key(viewer_tg_id)
    raw = await redis.lrange(key, 0, -1)
    return [int(x) for x in raw]


async def ensure_feed_queue_depth(
    redis: Redis,
    pool: asyncpg.Pool,
    viewer_tg_id: int,
    *,
    target_depth: int = FEED_QUEUE_SIZE,
) -> None:
    """Top up Redis list with ranked profile ids (same ordering as SQL feed)."""
    key = _feed_key(viewer_tg_id)
    while True:
        depth = int(await redis.llen(key))
        if depth >= target_depth:
            return
        exclude = await _queue_ids(redis, viewer_tg_id)
        need = target_depth - depth
        ids = await get_next_candidate_ids(
            pool,
            viewer_tg_id,
            need,
            exclude_profile_ids=exclude,
        )
        if not ids:
            return
        await redis.rpush(key, *[str(i) for i in ids])


async def pop_next_feed_candidate(
    redis: Redis,
    pool: asyncpg.Pool,
    viewer_tg_id: int,
) -> dict | None:
    """
    Take next id from Redis queue, validate in DB (full card path), drop stale ids.
    Refills queue toward FEED_QUEUE_SIZE after a successful card (batch cycle).
    """
    key = _feed_key(viewer_tg_id)
    for _ in range(25):
        await ensure_feed_queue_depth(redis, pool, viewer_tg_id)
        raw = await redis.lpop(key)
        if raw is None:
            return None
        profile_id = int(raw)
        card = await get_candidate_for_viewer(pool, viewer_tg_id, profile_id)
        if card is not None:
            await ensure_feed_queue_depth(redis, pool, viewer_tg_id)
            return card
        logger.debug("Dropped stale feed id %s for viewer %s", profile_id, viewer_tg_id)
    return None


async def clear_feed_queue(redis: Redis, viewer_tg_id: int) -> None:
    await redis.delete(_feed_key(viewer_tg_id))
