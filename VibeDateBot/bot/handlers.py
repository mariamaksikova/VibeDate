from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from bot.db import ensure_user_and_profile

log = logging.getLogger(__name__)

_REF_PREFIX = re.compile(r"^ref_(\d+)$", re.IGNORECASE)


def _parse_start_argument(text: str | None) -> int | None:
    if not text:
        return None
    text = text.strip()
    m = _REF_PREFIX.match(text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    u = update.effective_user
    pool = context.bot_data.get("db_pool")
    if pool is None:
        log.error("db_pool missing in bot_data")
        await update.message.reply_text(
            "Сервис временно недоступен. Попробуйте позже."
        )
        return

    ref_tg = None
    if context.args:
        ref_tg = _parse_start_argument(" ".join(context.args))

    try:
        is_new_profile, info = await ensure_user_and_profile(
            pool,
            tg_id=u.id,
            username=u.username,
            referred_by_tg_id=ref_tg,
        )
    except Exception:
        log.exception("ensure_user_and_profile failed for tg_id=%s", u.id)
        await update.message.reply_text(
            "Не удалось сохранить регистрацию. Проверьте базу данных и настройки."
        )
        return

    name = u.first_name or "друг"
    if is_new_profile:
        text = (
            f"Привет, {name}! Ты в VibeDate — добро пожаловать.\n\n"
            "Регистрация прошла: мы сохранили твой Telegram ID. "
            "Дальше можно будет заполнить анкету (этап 3).\n\n"
            "Команды: /help — что умеет бот."
        )
    else:
        text = (
            f"С возвращением, {name}!\n\n"
            "Твой аккаунт уже есть. Используй /help, чтобы посмотреть команды."
        )

    await update.message.reply_text(text)
    log.info(
        "start tg_id=%s new_profile=%s profile_id=%s",
        u.id,
        is_new_profile,
        info.get("profile_id"),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        "VibeDate — знакомства через Telegram.\n\n"
        "/start — регистрация или вход (по Telegram ID)\n"
        "/help — эта справка\n\n"
        "Скоро: заполнение анкеты, лента и мэтчи."
    )
