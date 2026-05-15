from __future__ import annotations

import logging

import asyncpg
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from redis.asyncio import Redis

from app.admin_access import is_admin, load_admin_tg_ids
from app.db import (
    get_admin_dashboard_stats,
    get_top_profiles_by_rating,
    get_user_admin_snapshot,
)
from app.tasks import recalculate_all_ratings

logger = logging.getLogger(__name__)

router = Router(name="admin")


async def _ensure_admin(message: Message) -> bool:
    user = message.from_user
    if user is None:
        return False

    admin_ids = load_admin_tg_ids()
    if is_admin(user.id, admin_ids):
        return True

    hint = (
        f"Нет доступа к админке.\n\n"
        f"Ваш Telegram ID: `{user.id}`\n"
        f"В `.env` должно быть:\n"
        f"`ADMIN_TG_IDS={user.id}`\n\n"
        f"После правки пересоздайте контейнер бота:\n"
        f"`docker compose up -d --force-recreate app`"
    )
    if not admin_ids:
        hint += "\n\nСейчас `ADMIN_TG_IDS` пуст — бот не видит ни одного админа."
    await message.answer(hint)
    logger.info("admin_denied tg_id=%s configured=%s", user.id, sorted(admin_ids))
    return False


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not await _ensure_admin(message):
        return
    await message.answer(
        "Панель администратора VibeDate\n\n"
        "/admin_stats — сводка по БД и Redis\n"
        "/admin_top — топ-5 анкет по combined_rating\n"
        "/admin_user <telegram_id> — карточка пользователя\n"
        "/admin_recalc — запустить пересчёт рейтингов (Celery)"
    )


@router.message(Command("admin_stats"))
async def cmd_admin_stats(
    message: Message,
    db_pool: asyncpg.Pool,
    redis: Redis | None = None,
) -> None:
    if not await _ensure_admin(message):
        return

    stats = await get_admin_dashboard_stats(db_pool)
    feed_queues = 0
    if redis is not None:
        try:
            async for _ in redis.scan_iter("vibedate:feed:*", count=100):
                feed_queues += 1
        except Exception as exc:
            logger.warning("admin_redis_scan_failed: %s", exc)

    await message.answer(
        "Статистика VibeDate\n\n"
        f"Пользователей: {stats['users_count']}\n"
        f"Анкет: {stats['profiles_count']}\n"
        f"Реакций (лайк+скип): {stats['likes_count']} "
        f"(лайков: {stats['likes_positive']})\n"
        f"Мэтчей: {stats['matches_count']}\n"
        f"Фото в MinIO: {stats['photos_count']}\n"
        f"Рефералов (пришли по ссылке): {stats['referrals_count']}\n"
        f"Средний combined_rating: {stats['avg_combined_rating'] or '—'}\n"
        f"Очередей ленты в Redis: {feed_queues}"
    )


@router.message(Command("admin_top"))
async def cmd_admin_top(message: Message, db_pool: asyncpg.Pool) -> None:
    if not await _ensure_admin(message):
        return

    rows = await get_top_profiles_by_rating(db_pool, limit=5)
    if not rows:
        await message.answer("В ratings пока нет данных.")
        return
    lines = ["Топ анкет по combined_rating:\n"]
    for i, row in enumerate(rows, start=1):
        city = row.get("city") or "—"
        lines.append(
            f"{i}. #{row['profile_id']} {row['title']} — "
            f"{row['combined_rating']} (лайков: {row['likes_received']}, "
            f"мэтчей: {row['matches_count']}, {city})"
        )
    await message.answer("\n".join(lines))


@router.message(Command("admin_user"))
async def cmd_admin_user(message: Message, db_pool: asyncpg.Pool) -> None:
    if not await _ensure_admin(message):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("Формат: /admin_user <telegram_id>")
        return
    target_tg_id = int(parts[1].strip())
    row = await get_user_admin_snapshot(db_pool, target_tg_id)
    if row is None:
        await message.answer(f"Пользователь tg_id={target_tg_id} не найден.")
        return
    if row.get("profile_id") is None:
        await message.answer(
            f"tg_id={target_tg_id}, user_id={row['user_id']}, "
            f"username=@{row['username'] or '—'}\nАнкета ещё не создана."
        )
        return
    await message.answer(
        f"Пользователь tg_id={row['tg_id']}\n"
        f"user_id={row['user_id']}, profile_id={row['profile_id']}\n"
        f"username=@{row['username'] or '—'}\n"
        f"имя: {row['display_name'] or '—'}, город: {row['city'] or '—'}\n"
        f"заполненность: {row['completeness_score']}%, фото: {row['photo_count']}\n"
        f"рейтинг: primary={row['primary_rating']}, "
        f"combined={row['combined_rating']}\n"
        f"лайки/скипы/мэтчи/диалоги: "
        f"{row['likes_received']}/{row['skips_received']}/"
        f"{row['matches_count']}/{row['dialogs_started']}\n"
        f"реф. код: {row['referral_code']}, пригласил: {row['invited_count']}"
    )


@router.message(Command("admin_recalc"))
async def cmd_admin_recalc(message: Message) -> None:
    if not await _ensure_admin(message):
        return

    try:
        task = recalculate_all_ratings.delay()
    except Exception as exc:
        logger.exception("admin_recalc_failed")
        await message.answer(f"Не удалось поставить задачу Celery: {exc}")
        return
    await message.answer(
        f"Задача пересчёта рейтингов отправлена в Celery.\n"
        f"task_id: {task.id}"
    )
