import asyncio
from collections.abc import Callable

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CacheMode, settings
from app.metrics import metrics
from app.models import Item


def _cache_key(item_id: int) -> str:
    return f"{settings.item_key_prefix}{item_id}"


WB_DIRTY_KEY = "wb:dirty_ids"


async def _redis_get(r: Redis, item_id: int) -> str | None:
    return await r.get(_cache_key(item_id))


async def _redis_set(r: Redis, item_id: int, value: str) -> None:
    await r.set(_cache_key(item_id), value, ex=settings.cache_ttl_sec)


async def _redis_delete(r: Redis, item_id: int) -> None:
    await r.delete(_cache_key(item_id))


async def read_cache_aside(session: AsyncSession, r: Redis, item_id: int) -> str | None:
    cached = await _redis_get(r, item_id)
    if cached is not None:
        metrics.record_cache_hit()
        return cached
    metrics.record_cache_miss()
    row = (await session.execute(select(Item).where(Item.id == item_id))).scalar_one_or_none()
    metrics.inc_db_read()
    if row is None:
        return None
    await _redis_set(r, item_id, row.value)
    return row.value


async def write_cache_aside(session: AsyncSession, r: Redis, item_id: int, value: str) -> None:
    await session.merge(Item(id=item_id, value=value))
    await session.commit()
    metrics.inc_db_write()
    await _redis_delete(r, item_id)


async def read_write_through(session: AsyncSession, r: Redis, item_id: int) -> str | None:
    return await read_cache_aside(session, r, item_id)


async def write_write_through(session: AsyncSession, r: Redis, item_id: int, value: str) -> None:
    await session.merge(Item(id=item_id, value=value))
    await session.commit()
    metrics.inc_db_write()
    await _redis_set(r, item_id, value)


async def read_write_back(session: AsyncSession, r: Redis, item_id: int) -> str | None:
    cached = await _redis_get(r, item_id)
    if cached is not None:
        metrics.record_cache_hit()
        return cached
    metrics.record_cache_miss()
    row = (await session.execute(select(Item).where(Item.id == item_id))).scalar_one_or_none()
    metrics.inc_db_read()
    if row is None:
        return None
    await _redis_set(r, item_id, row.value)
    return row.value


async def write_write_back(_session: AsyncSession, r: Redis, item_id: int, value: str) -> None:
    await _redis_set(r, item_id, value)
    await r.sadd(WB_DIRTY_KEY, str(item_id))
    pending = int(await r.scard(WB_DIRTY_KEY))
    metrics.update_write_back_pending_peak(pending)


async def flush_write_back(session: AsyncSession, r: Redis) -> None:
    ids_raw = list(await r.smembers(WB_DIRTY_KEY))
    if not ids_raw:
        return
    to_remove: list[str] = []
    rows = 0
    for sid in ids_raw:
        item_id = int(sid)
        val = await r.get(_cache_key(item_id))
        if val is None:
            to_remove.append(sid)
            continue
        await session.merge(Item(id=item_id, value=val))
        rows += 1
        to_remove.append(sid)
    if rows:
        await session.commit()
        metrics.inc_db_write(rows)
    for sid in to_remove:
        await r.srem(WB_DIRTY_KEY, sid)
    dirty_left = int(await r.scard(WB_DIRTY_KEY))
    metrics.record_write_back_flush(rows, dirty_left)


def get_read_fn() -> Callable:
    m = {
        CacheMode.CACHE_ASIDE: read_cache_aside,
        CacheMode.WRITE_THROUGH: read_write_through,
        CacheMode.WRITE_BACK: read_write_back,
    }
    return m[settings.cache_mode]


def get_write_fn() -> Callable:
    m = {
        CacheMode.CACHE_ASIDE: write_cache_aside,
        CacheMode.WRITE_THROUGH: write_write_through,
        CacheMode.WRITE_BACK: write_write_back,
    }
    return m[settings.cache_mode]


_flush_task: asyncio.Task | None = None


async def _write_back_loop(stop: asyncio.Event) -> None:
    from app.database import SessionLocal
    from app.redis_client import get_redis

    while not stop.is_set():
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.write_back_flush_interval_sec
            )
        except TimeoutError:
            pass
        if stop.is_set():
            break
        async with SessionLocal() as session:
            r = await get_redis()
            await flush_write_back(session, r)


def start_write_back_flusher() -> tuple[asyncio.Event, asyncio.Task]:
    global _flush_task
    stop = asyncio.Event()
    _flush_task = asyncio.create_task(_write_back_loop(stop))
    return stop, _flush_task


async def stop_write_back_flusher(stop: asyncio.Event) -> None:
    global _flush_task
    stop.set()
    if _flush_task is not None:
        await asyncio.wait_for(_flush_task, timeout=5.0)
        _flush_task = None


async def final_flush_write_back() -> None:
    if settings.cache_mode != CacheMode.WRITE_BACK:
        return
    from app.database import SessionLocal
    from app.redis_client import get_redis

    async with SessionLocal() as session:
        r = await get_redis()
        await flush_write_back(session, r)
