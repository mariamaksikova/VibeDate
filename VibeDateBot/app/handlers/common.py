from __future__ import annotations

import logging

import asyncpg
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from app.db import ensure_user_and_profile
from app.keyboards.main import main_menu_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return

    try:
        is_new, info = await ensure_user_and_profile(
            pool=db_pool,
            tg_id=message.from_user.id,
            username=message.from_user.username,
        )
    except Exception:
        logger.exception("Registration failed for tg_id=%s", message.from_user.id)
        await message.answer("Не удалось сохранить пользователя в БД. Проверь логи app.")
        return

    logger.info(
        "start processed tg_id=%s is_new=%s user_id=%s profile_id=%s",
        message.from_user.id,
        is_new,
        info.get("user_id"),
        info.get("profile_id"),
    )
    if is_new:
        await message.answer(
            "Привет! Ты успешно зарегистрирован(а) в VibeDate.\n"
            "Следующий шаг: заполни анкету кнопкой 'Заполнить анкету'.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(
            "С возвращением! Твоя анкета уже есть в системе.\n"
            "Используй кнопки меню или /help.",
            reply_markup=main_menu_keyboard(),
        )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "VibeDate Bot\n\n"
        "/start - регистрация или вход\n"
        "/my_profile - показать анкету\n"
        "/set_age 22\n"
        "/set_gender м|ж\n"
        "/set_city Москва\n"
        "/set_interests музыка,спорт\n"
        "/set_bio Текст о себе\n"
        "/set_looking_for м|ж\n"
        "/set_range 18 30\n"
        "/feed - следующая анкета\n"
        "/like <profile_id>\n"
        "/skip <profile_id>\n"
        "\nИли используй кнопки: 'Моя анкета', 'Заполнить анкету', 'Лента анкет'.\n"
        "/help - справка"
    )
