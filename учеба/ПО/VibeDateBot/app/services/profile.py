from __future__ import annotations

import asyncpg

from app.services.rating import calc_behavior_rating, calc_combined_rating, calc_primary_rating


def _profile_completeness(
    age: int | None,
    gender: str | None,
    city: str | None,
    interests: str | None,
    bio: str | None,
) -> int:
    filled = sum([bool(age), bool(gender), bool(city), bool(interests), bool(bio)])
    return int((filled / 5) * 100)


async def refresh_profile_rating(pool: asyncpg.Pool, profile_id: int) -> None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                p.age,
                p.gender,
                p.city,
                p.interests,
                p.bio,
                p.looking_for,
                p.photo_count,
                COALESCE(r.likes_received, 0) AS likes_received,
                COALESCE(r.skips_received, 0) AS skips_received,
                COALESCE(r.matches_count, 0) AS matches_count,
                COALESCE(r.dialogs_started, 0) AS dialogs_started
            FROM profiles p
            LEFT JOIN ratings r ON r.profile_id = p.id
            WHERE p.id = $1
            """,
            profile_id,
        )
        if row is None:
            return

        completeness = _profile_completeness(
            age=row["age"],
            gender=row["gender"],
            city=row["city"],
            interests=row["interests"],
            bio=row["bio"],
        )
        primary = calc_primary_rating(
            age=row["age"],
            interests=row["interests"],
            city=row["city"],
            looking_for=row["looking_for"],
            photo_count=row["photo_count"] or 0,
            profile_completeness=completeness,
        )
        behavior = calc_behavior_rating(
            likes_received=row["likes_received"],
            skips_received=row["skips_received"],
            matches_count=row["matches_count"],
            dialogs_started=row["dialogs_started"],
        )
        combined = calc_combined_rating(primary, behavior)

        await conn.execute(
            """
            UPDATE profiles
            SET completeness_score = $2, primary_rating = $3, updated_at = NOW()
            WHERE id = $1
            """,
            profile_id,
            completeness,
            primary,
        )
        await conn.execute(
            """
            INSERT INTO ratings (
                profile_id, primary_rating, combined_rating, updated_at
            )
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (profile_id) DO UPDATE SET
                primary_rating = EXCLUDED.primary_rating,
                combined_rating = EXCLUDED.combined_rating,
                updated_at = NOW()
            """,
            profile_id,
            primary,
            combined,
        )
