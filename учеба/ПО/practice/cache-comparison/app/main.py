from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CacheMode, settings
from app.database import SessionLocal, get_session, init_db
from app.metrics import metrics
from app.redis_client import close_redis, get_redis
from app.service import WB_DIRTY_KEY, final_flush_write_back, start_write_back_flusher, stop_write_back_flusher
from app.service import get_read_fn, get_write_fn

_wb_stop = None
_wb_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _wb_stop, _wb_task
    await init_db()
    from app.seed import ensure_seeded

    async with SessionLocal() as session:
        await ensure_seeded(session)
    await get_redis()
    if settings.cache_mode == CacheMode.WRITE_BACK:
        _wb_stop, _wb_task = start_write_back_flusher()
    yield
    if settings.cache_mode == CacheMode.WRITE_BACK and _wb_stop is not None:
        await stop_write_back_flusher(_wb_stop)
        await final_flush_write_back()
    await close_redis()


app = FastAPI(title="Cache comparison bench", lifespan=lifespan)


class ItemBody(BaseModel):
    value: str


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "mode": settings.cache_mode.value}


@app.get("/items/{item_id}")
async def get_item(
    item_id: int,
    session: AsyncSession = Depends(get_session),
    r: Redis = Depends(get_redis),
) -> dict:
    read_fn = get_read_fn()
    value = await read_fn(session, r, item_id)
    if value is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"id": item_id, "value": value}


@app.put("/items/{item_id}")
async def put_item(
    item_id: int,
    body: ItemBody,
    session: AsyncSession = Depends(get_session),
    r: Redis = Depends(get_redis),
) -> dict:
    write_fn = get_write_fn()
    await write_fn(session, r, item_id, body.value)
    return {"id": item_id, "value": body.value}


@app.get("/stats")
async def stats(r: Redis = Depends(get_redis)) -> dict:
    snap = metrics.snapshot()
    snap["mode"] = settings.cache_mode.value
    if settings.cache_mode == CacheMode.WRITE_BACK:
        snap["write_back_dirty_now"] = int(await r.scard(WB_DIRTY_KEY))
    return snap


@app.post("/admin/reset")
async def admin_reset(
    session: AsyncSession = Depends(get_session),
    r: Redis = Depends(get_redis),
) -> dict:
    from sqlalchemy import delete

    from app.models import Item
    from app.seed import reseed_items

    metrics.reset()
    await r.flushdb()
    await session.execute(delete(Item))
    await reseed_items(session)
    await session.commit()
    return {"ok": True}


@app.post("/admin/final-flush")
async def admin_final_flush() -> dict:
    if settings.cache_mode != CacheMode.WRITE_BACK:
        return {"skipped": True}
    await final_flush_write_back()
    return {"ok": True}
