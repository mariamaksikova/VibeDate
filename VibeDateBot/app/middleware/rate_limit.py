from __future__ import annotations

import structlog
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

MAX_UPDATES_PER_MINUTE = 30


class RateLimitMiddleware(BaseMiddleware):
    """Redis INCR + EXPIRE: защита от спама кнопками (отдельно от Celery)."""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        redis: Redis | None = data.get("redis")
        user = getattr(event, "from_user", None)
        if redis is None or user is None:
            return await handler(event, data)

        key = f"vibedate:rl:{user.id}"
        count = int(await redis.incr(key))
        if count == 1:
            await redis.expire(key, 60)
        if count > MAX_UPDATES_PER_MINUTE:
            if isinstance(event, Message):
                await event.answer("Слишком много действий. Подожди минуту и попробуй снова.")
            logger.warning("rate_limit_exceeded", tg_id=user.id, count=count)
            return None
        return await handler(event, data)
