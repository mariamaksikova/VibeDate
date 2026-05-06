import os

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item

SEED_COUNT = int(os.environ.get("BENCH_SEED_COUNT", "5000"))


async def reseed_items(session: AsyncSession) -> int:
    for i in range(1, SEED_COUNT + 1):
        session.add(Item(id=i, value=f"seed-{i}"))
    return SEED_COUNT


async def ensure_seeded(session: AsyncSession) -> None:
    cnt = await session.scalar(select(func.count()).select_from(Item))
    if (cnt or 0) == 0:
        await reseed_items(session)
        await session.commit()
