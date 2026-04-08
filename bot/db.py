from __future__ import annotations

import logging
from typing import Any

import asyncpg

log = logging.getLogger(__name__)


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=1, max_size=10)


async def ensure_user_and_profile(
    pool: asyncpg.Pool,
    tg_id: int,
    username: str | None,
    referred_by_tg_id: int | None = None,
) -> tuple[bool, dict[str, Any]]:
    """
    Upsert user by Telegram id; create profile + ratings row if missing.

    Returns (created_new_profile, info dict with user_id, profile_id).
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO users (tg_id, username)
                VALUES ($1, $2)
                ON CONFLICT (tg_id) DO UPDATE SET
                    username = COALESCE(EXCLUDED.username, users.username)
                """,
                tg_id,
                username,
            )

            if referred_by_tg_id is not None and referred_by_tg_id != tg_id:
                referrer = await conn.fetchrow(
                    "SELECT id FROM users WHERE tg_id = $1",
                    referred_by_tg_id,
                )
                if referrer is not None:
                    await conn.execute(
                        """
                        UPDATE users SET referred_by = $2
                        WHERE tg_id = $1 AND referred_by IS NULL
                        """,
                        tg_id,
                        referrer["id"],
                    )

            user_row = await conn.fetchrow(
                "SELECT id FROM users WHERE tg_id = $1",
                tg_id,
            )
            assert user_row is not None
            user_pk: int = user_row["id"]

            existing = await conn.fetchrow(
                "SELECT id FROM profiles WHERE user_id = $1",
                tg_id,
            )
            if existing is not None:
                log.debug("Profile already exists for tg_id=%s", tg_id)
                return False, {
                    "user_pk": user_pk,
                    "profile_id": existing["id"],
                }

            profile = await conn.fetchrow(
                """
                INSERT INTO profiles (user_id)
                VALUES ($1)
                RETURNING id
                """,
                tg_id,
            )
            assert profile is not None
            profile_id: int = profile["id"]

            await conn.execute(
                "INSERT INTO ratings (profile_id) VALUES ($1)",
                profile_id,
            )
            log.info("Registered new profile_id=%s for tg_id=%s", profile_id, tg_id)
            return True, {"user_pk": user_pk, "profile_id": profile_id}
