from __future__ import annotations

import secrets
from typing import Any

import asyncpg


def normalize_database_url(raw_dsn: str) -> str:
    """Convert SQLAlchemy style DSN to asyncpg-compatible DSN."""
    return raw_dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


async def create_pool(dsn: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(normalize_database_url(dsn), min_size=1, max_size=10)
    await ensure_runtime_schema(pool)
    return pool


async def ensure_runtime_schema(pool: asyncpg.Pool) -> None:
    """Apply lightweight runtime migrations for local development."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            ALTER TABLE profiles
            ADD COLUMN IF NOT EXISTS display_name VARCHAR(80)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS photos (
                id         SERIAL PRIMARY KEY,
                profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                s3_key     TEXT NOT NULL,
                is_main    BOOLEAN DEFAULT FALSE,
                order_num  INTEGER DEFAULT 1
            )
            """
        )
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_likes_from_profile ON likes(from_profile)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_likes_to_profile ON likes(to_profile)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_profiles_updated_at ON profiles(updated_at DESC)")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_photos_profile ON photos(profile_id)"
        )


def _new_referral_code() -> str:
    return secrets.token_urlsafe(6).replace("-", "")[:10]


async def ensure_user_and_profile(
    pool: asyncpg.Pool,
    tg_id: int,
    username: str | None,
    *,
    referral_code_from_start: str | None = None,
) -> tuple[bool, dict[str, Any]]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            user = await conn.fetchrow(
                """
                INSERT INTO users (tg_id, username, referral_code)
                VALUES ($1, $2, $3)
                ON CONFLICT (tg_id) DO UPDATE SET
                    username = COALESCE(EXCLUDED.username, users.username),
                    referral_code = COALESCE(users.referral_code, EXCLUDED.referral_code)
                RETURNING id, referral_code
                """,
                tg_id,
                username,
                _new_referral_code(),
            )
            assert user is not None
            user_id: int = user["id"]

            profile = await conn.fetchrow(
                "SELECT id FROM profiles WHERE user_id = $1",
                user_id,
            )
            if profile is not None:
                return False, {
                    "user_id": user_id,
                    "profile_id": profile["id"],
                    "referral_code": user["referral_code"],
                }

            referrer_id: int | None = None
            if referral_code_from_start:
                referrer_id = await conn.fetchval(
                    "SELECT id FROM users WHERE referral_code = $1 AND id <> $2",
                    referral_code_from_start,
                    user_id,
                )

            await conn.execute(
                """
                UPDATE users
                SET referred_by = COALESCE(referred_by, $2)
                WHERE id = $1 AND referred_by IS NULL
                """,
                user_id,
                referrer_id,
            )

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
            return True, {
                "user_id": user_id,
                "profile_id": profile_id,
                "referral_code": user["referral_code"],
            }


async def count_referrals_for_user(pool: asyncpg.Pool, user_id: int) -> int:
    async with pool.acquire() as conn:
        value = await conn.fetchval(
            "SELECT COUNT(*)::int FROM users WHERE referred_by = $1",
            user_id,
        )
        return int(value or 0)


async def get_activity_peak_share(pool: asyncpg.Pool, profile_id: int) -> float:
    """Доля лайков в самый активный час суток (уровень 2 — время активности)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT EXTRACT(HOUR FROM created_at)::int AS hour, COUNT(*)::int AS cnt
            FROM likes
            WHERE to_profile = $1 AND is_like = TRUE
            GROUP BY hour
            """,
            profile_id,
        )
        if not rows:
            return 0.0
        counts = [int(r["cnt"]) for r in rows]
        total = sum(counts)
        if total == 0:
            return 0.0
        return max(counts) / total


async def get_profile_by_tg_id(pool: asyncpg.Pool, tg_id: int) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                p.id,
                p.user_id,
                p.display_name,
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
                p.primary_rating,
                u.username,
                u.referral_code
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
        "display_name",
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
                p.display_name,
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
              AND p.display_name IS NOT NULL
              AND p.age IS NOT NULL
              AND p.gender IS NOT NULL
              AND p.city IS NOT NULL
              AND p.interests IS NOT NULL
              AND p.bio IS NOT NULL
              AND p.looking_for IS NOT NULL
              AND p.min_age IS NOT NULL
              AND p.max_age IS NOT NULL
              AND ($2::int IS NULL OR p.age >= $2)
              AND ($3::int IS NULL OR p.age <= $3)
              AND ($4::text IS NULL OR $4::text = '' OR $4::text = 'a' OR p.gender = $4::text)
              AND (
                  p.looking_for IS NULL
                  OR p.looking_for = ''
                  OR p.looking_for = 'a'
                  OR ($5::text IS NOT NULL AND p.looking_for = $5::text)
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM likes l
                  WHERE l.from_profile = $1 AND l.to_profile = p.id
              )
            ORDER BY
                CASE WHEN $6::text IS NOT NULL AND p.city = $6 THEN 1 ELSE 0 END DESC,
                COALESCE(r.combined_rating, 1000) DESC,
                p.updated_at DESC
            LIMIT 1
            """,
            viewer["id"],
            viewer["min_age"],
            viewer["max_age"],
            viewer["looking_for"],
            viewer["gender"],
            viewer["city"],
        )
        return dict(row) if row else None


_FEED_CANDIDATE_SQL = """
            FROM profiles p
            JOIN users u ON u.id = p.user_id
            LEFT JOIN ratings r ON r.profile_id = p.id
            WHERE p.id <> $1
              AND p.display_name IS NOT NULL
              AND p.age IS NOT NULL
              AND p.gender IS NOT NULL
              AND p.city IS NOT NULL
              AND p.interests IS NOT NULL
              AND p.bio IS NOT NULL
              AND p.looking_for IS NOT NULL
              AND p.min_age IS NOT NULL
              AND p.max_age IS NOT NULL
              AND ($2::int IS NULL OR p.age >= $2)
              AND ($3::int IS NULL OR p.age <= $3)
              AND ($4::text IS NULL OR $4::text = '' OR $4::text = 'a' OR p.gender = $4::text)
              AND (
                  p.looking_for IS NULL
                  OR p.looking_for = ''
                  OR p.looking_for = 'a'
                  OR ($5::text IS NOT NULL AND p.looking_for = $5::text)
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM likes l
                  WHERE l.from_profile = $1 AND l.to_profile = p.id
              )
"""


async def get_next_candidate_ids(
    pool: asyncpg.Pool,
    viewer_tg_id: int,
    limit: int,
    *,
    exclude_profile_ids: list[int] | None = None,
) -> list[int]:
    """Return ranked profile ids for feed prefetch (Redis batch)."""
    exclude_profile_ids = exclude_profile_ids or []
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
            return []

        rows = await conn.fetch(
            f"""
            SELECT p.id
            {_FEED_CANDIDATE_SQL}
              AND (cardinality($6::int[]) = 0 OR NOT (p.id = ANY($6::int[])))
            ORDER BY
                CASE WHEN $7::text IS NOT NULL AND p.city = $7 THEN 1 ELSE 0 END DESC,
                COALESCE(r.combined_rating, 1000) DESC,
                p.updated_at DESC
            LIMIT $8
            """,
            viewer["id"],
            viewer["min_age"],
            viewer["max_age"],
            viewer["looking_for"],
            viewer["gender"],
            exclude_profile_ids,
            viewer["city"],
            limit,
        )
        return [int(r["id"]) for r in rows]


async def get_candidate_for_viewer(
    pool: asyncpg.Pool,
    viewer_tg_id: int,
    candidate_profile_id: int,
) -> dict[str, Any] | None:
    """Load one feed card if it still matches viewer rules (after Redis prefetch)."""
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
            f"""
            SELECT
                p.id AS profile_id,
                u.tg_id,
                u.username,
                p.display_name,
                p.age,
                p.gender,
                p.city,
                p.interests,
                p.bio,
                COALESCE(r.combined_rating, 1000) AS combined_rating
            {_FEED_CANDIDATE_SQL}
              AND p.id = $6
            """,
            viewer["id"],
            viewer["min_age"],
            viewer["max_age"],
            viewer["looking_for"],
            viewer["gender"],
            candidate_profile_id,
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

            previous_reaction = await conn.fetchval(
                """
                SELECT is_like
                FROM likes
                WHERE from_profile = $1 AND to_profile = $2
                """,
                from_profile_id,
                to_profile_id,
            )

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

            if previous_reaction is None:
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
            elif previous_reaction != is_like:
                if previous_reaction:
                    await conn.execute(
                        """
                        UPDATE ratings
                        SET
                            likes_received = GREATEST(likes_received - 1, 0),
                            skips_received = skips_received + 1,
                            updated_at = NOW()
                        WHERE profile_id = $1
                        """,
                        to_profile_id,
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE ratings
                        SET
                            skips_received = GREATEST(skips_received - 1, 0),
                            likes_received = likes_received + 1,
                            updated_at = NOW()
                        WHERE profile_id = $1
                        """,
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
            match_contacts: dict[str, Any] | None = None
            if is_like and mutual_like:
                p1, p2 = sorted([from_profile_id, to_profile_id])
                inserted_match_id = await conn.fetchval(
                    """
                    INSERT INTO matches (profile1, profile2)
                    VALUES ($1, $2)
                    ON CONFLICT (profile1, profile2) DO NOTHING
                    RETURNING id
                    """,
                    p1,
                    p2,
                )
                if inserted_match_id is not None:
                    await conn.execute(
                        "UPDATE ratings SET matches_count = matches_count + 1, dialogs_started = dialogs_started + 1, updated_at = NOW() WHERE profile_id = ANY($1::int[])",
                        [from_profile_id, to_profile_id],
                    )
                is_match = True
                contact_rows = await conn.fetch(
                    """
                    SELECT
                        p.id AS profile_id,
                        p.display_name,
                        u.tg_id,
                        u.username
                    FROM profiles p
                    JOIN users u ON u.id = p.user_id
                    WHERE p.id = ANY($1::int[])
                    """,
                    [from_profile_id, to_profile_id],
                )
                contacts_by_profile = {row["profile_id"]: dict(row) for row in contact_rows}
                match_contacts = {
                    "from_user": contacts_by_profile.get(from_profile_id),
                    "to_user": contacts_by_profile.get(to_profile_id),
                }

            return {
                "from_profile_id": from_profile_id,
                "to_profile_id": to_profile_id,
                "is_match": is_match,
                "match_contacts": match_contacts,
            }


async def add_profile_photo_by_tg_id(
    pool: asyncpg.Pool,
    tg_id: int,
    s3_key: str,
) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            profile = await conn.fetchrow(
                """
                SELECT p.id
                FROM users u
                JOIN profiles p ON p.user_id = u.id
                WHERE u.tg_id = $1
                """,
                tg_id,
            )
            if profile is None:
                return None
            profile_id = int(profile["id"])
            count = int(
                await conn.fetchval("SELECT COUNT(*) FROM photos WHERE profile_id = $1", profile_id) or 0
            )
            if count >= 5:
                return {"profile_id": profile_id, "photo_count": count, "saved": False}

            await conn.execute(
                """
                INSERT INTO photos (profile_id, s3_key, is_main, order_num)
                VALUES ($1, $2, $3, $4)
                """,
                profile_id,
                s3_key,
                count == 0,
                count + 1,
            )
            new_count = count + 1
            await conn.execute(
                """
                UPDATE profiles
                SET photo_count = $2, updated_at = NOW()
                WHERE id = $1
                """,
                profile_id,
                new_count,
            )
            return {"profile_id": profile_id, "photo_count": new_count, "saved": True}


async def get_profile_photos_by_tg_id(pool: asyncpg.Pool, tg_id: int) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ph.id, ph.s3_key, ph.is_main, ph.order_num
            FROM users u
            JOIN profiles p ON p.user_id = u.id
            JOIN photos ph ON ph.profile_id = p.id
            WHERE u.tg_id = $1
            ORDER BY ph.order_num, ph.id
            """,
            tg_id,
        )
        return [dict(row) for row in rows]


async def get_admin_dashboard_stats(pool: asyncpg.Pool) -> dict[str, int | float | None]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*)::int FROM users) AS users_count,
                (SELECT COUNT(*)::int FROM profiles) AS profiles_count,
                (SELECT COUNT(*)::int FROM likes) AS likes_count,
                (SELECT COUNT(*)::int FROM likes WHERE is_like = TRUE) AS likes_positive,
                (SELECT COUNT(*)::int FROM matches) AS matches_count,
                (SELECT COUNT(*)::int FROM photos) AS photos_count,
                (SELECT COUNT(*)::int FROM users WHERE referred_by IS NOT NULL) AS referrals_count,
                (SELECT ROUND(AVG(combined_rating)::numeric, 1) FROM ratings) AS avg_combined_rating
            """
        )
    assert row is not None
    return dict(row)


async def get_top_profiles_by_rating(pool: asyncpg.Pool, *, limit: int = 5) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                p.id AS profile_id,
                COALESCE(p.display_name, u.username, 'без имени') AS title,
                r.combined_rating,
                r.primary_rating,
                r.likes_received,
                r.matches_count,
                p.city
            FROM ratings r
            JOIN profiles p ON p.id = r.profile_id
            JOIN users u ON u.id = p.user_id
            ORDER BY r.combined_rating DESC, p.id
            LIMIT $1
            """,
            limit,
        )
    return [dict(row) for row in rows]


async def get_user_admin_snapshot(pool: asyncpg.Pool, tg_id: int) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                u.id AS user_id,
                u.tg_id,
                u.username,
                u.referral_code,
                u.referred_by,
                u.created_at AS user_created_at,
                p.id AS profile_id,
                p.display_name,
                p.city,
                p.completeness_score,
                p.photo_count,
                r.primary_rating,
                r.combined_rating,
                r.likes_received,
                r.skips_received,
                r.matches_count,
                r.dialogs_started,
                (SELECT COUNT(*)::int FROM users ref WHERE ref.referred_by = u.id) AS invited_count
            FROM users u
            LEFT JOIN profiles p ON p.user_id = u.id
            LEFT JOIN ratings r ON r.profile_id = p.id
            WHERE u.tg_id = $1
            """,
            tg_id,
        )
    return dict(row) if row else None
