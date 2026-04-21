from __future__ import annotations

from typing import Any

import asyncpg


def normalize_database_url(raw_dsn: str) -> str:
    """Convert SQLAlchemy style DSN to asyncpg-compatible DSN."""
    return raw_dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(normalize_database_url(dsn), min_size=1, max_size=10)


async def ensure_user_and_profile(
    pool: asyncpg.Pool,
    tg_id: int,
    username: str | None,
) -> tuple[bool, dict[str, Any]]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            user = await conn.fetchrow(
                """
                INSERT INTO users (tg_id, username)
                VALUES ($1, $2)
                ON CONFLICT (tg_id) DO UPDATE SET
                    username = COALESCE(EXCLUDED.username, users.username)
                RETURNING id
                """,
                tg_id,
                username,
            )
            assert user is not None
            user_id: int = user["id"]

            profile = await conn.fetchrow(
                "SELECT id FROM profiles WHERE user_id = $1",
                user_id,
            )
            if profile is not None:
                return False, {"user_id": user_id, "profile_id": profile["id"]}

            profile = await conn.fetchrow(
                "INSERT INTO profiles (user_id) VALUES ($1) RETURNING id",
                user_id,
            )
            assert profile is not None
            profile_id: int = profile["id"]

            await conn.execute(
                "INSERT INTO ratings (profile_id) VALUES ($1) ON CONFLICT (profile_id) DO NOTHING",
                profile_id,
            )
            return True, {"user_id": user_id, "profile_id": profile_id}


async def get_profile_by_tg_id(pool: asyncpg.Pool, tg_id: int) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                p.id,
                p.user_id,
                p.age,
                p.gender,
                p.city,
                p.interests,
                p.bio,
                p.min_age,
                p.max_age,
                p.looking_for,
                p.photo_count,
                p.completeness_score,
                p.primary_rating
            FROM users u
            JOIN profiles p ON p.user_id = u.id
            WHERE u.tg_id = $1
            """,
            tg_id,
        )
        return dict(row) if row else None


async def update_profile_field(
    pool: asyncpg.Pool,
    tg_id: int,
    field: str,
    value: Any,
) -> dict[str, Any] | None:
    allowed_fields = {
        "age",
        "gender",
        "city",
        "interests",
        "bio",
        "min_age",
        "max_age",
        "looking_for",
    }
    if field not in allowed_fields:
        raise ValueError(f"Unsupported field: {field}")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE profiles p
            SET {field} = $2, updated_at = NOW()
            FROM users u
            WHERE p.user_id = u.id AND u.tg_id = $1
            RETURNING p.id, p.user_id
            """,
            tg_id,
            value,
        )
        return dict(row) if row else None


async def get_next_candidate(pool: asyncpg.Pool, viewer_tg_id: int) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        viewer = await conn.fetchrow(
            """
            SELECT p.id, p.gender, p.city, p.min_age, p.max_age, p.looking_for
            FROM users u
            JOIN profiles p ON p.user_id = u.id
            WHERE u.tg_id = $1
            """,
            viewer_tg_id,
        )
        if viewer is None:
            return None

        row = await conn.fetchrow(
            """
            SELECT
                p.id AS profile_id,
                u.tg_id,
                u.username,
                p.age,
                p.gender,
                p.city,
                p.interests,
                p.bio,
                COALESCE(r.combined_rating, 1000) AS combined_rating
            FROM profiles p
            JOIN users u ON u.id = p.user_id
            LEFT JOIN ratings r ON r.profile_id = p.id
            WHERE p.id <> $1
              AND ($2::int IS NULL OR p.age IS NULL OR p.age >= $2)
              AND ($3::int IS NULL OR p.age IS NULL OR p.age <= $3)
              AND NOT EXISTS (
                  SELECT 1
                  FROM likes l
                  WHERE l.from_profile = $1 AND l.to_profile = p.id
              )
            ORDER BY
                CASE WHEN $4::text IS NOT NULL AND p.gender = $4 THEN 1 ELSE 0 END DESC,
                CASE WHEN $5::text IS NOT NULL AND p.city = $5 THEN 1 ELSE 0 END DESC,
                COALESCE(r.combined_rating, 1000) DESC,
                p.updated_at DESC
            LIMIT 1
            """,
            viewer["id"],
            viewer["min_age"],
            viewer["max_age"],
            viewer["looking_for"],
            viewer["city"],
        )
        return dict(row) if row else None


async def react_to_candidate(
    pool: asyncpg.Pool,
    from_tg_id: int,
    to_profile_id: int,
    is_like: bool,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            actor = await conn.fetchrow(
                """
                SELECT p.id
                FROM users u
                JOIN profiles p ON p.user_id = u.id
                WHERE u.tg_id = $1
                """,
                from_tg_id,
            )
            if actor is None:
                raise RuntimeError("Actor profile not found")

            from_profile_id = actor["id"]
            if from_profile_id == to_profile_id:
                raise RuntimeError("Self reaction is not allowed")

            await conn.execute(
                """
                INSERT INTO likes (from_profile, to_profile, is_like)
                VALUES ($1, $2, $3)
                ON CONFLICT (from_profile, to_profile) DO UPDATE
                SET is_like = EXCLUDED.is_like, created_at = NOW()
                """,
                from_profile_id,
                to_profile_id,
                is_like,
            )

            await conn.execute(
                "INSERT INTO ratings (profile_id) VALUES ($1) ON CONFLICT (profile_id) DO NOTHING",
                to_profile_id,
            )

            if is_like:
                await conn.execute(
                    "UPDATE ratings SET likes_received = likes_received + 1, updated_at = NOW() WHERE profile_id = $1",
                    to_profile_id,
                )
            else:
                await conn.execute(
                    "UPDATE ratings SET skips_received = skips_received + 1, updated_at = NOW() WHERE profile_id = $1",
                    to_profile_id,
                )

            mutual_like = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM likes
                    WHERE from_profile = $1 AND to_profile = $2 AND is_like = TRUE
                )
                """,
                to_profile_id,
                from_profile_id,
            )

            is_match = False
            if is_like and mutual_like:
                p1, p2 = sorted([from_profile_id, to_profile_id])
                await conn.execute(
                    """
                    INSERT INTO matches (profile1, profile2)
                    VALUES ($1, $2)
                    ON CONFLICT (profile1, profile2) DO NOTHING
                    """,
                    p1,
                    p2,
                )
                await conn.execute(
                    "UPDATE ratings SET matches_count = matches_count + 1, updated_at = NOW() WHERE profile_id = ANY($1::int[])",
                    [from_profile_id, to_profile_id],
                )
                is_match = True

            return {
                "from_profile_id": from_profile_id,
                "to_profile_id": to_profile_id,
                "is_match": is_match,
            }
