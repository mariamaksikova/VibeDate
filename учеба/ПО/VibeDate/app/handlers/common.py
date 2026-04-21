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
            "Привет! Добро пожаловать в VibeDate.\n"
            "Давай соберем классную анкету: нажми 'Заполнить анкету'.\n"
            "Потом можно редактировать поля и добавлять фото отдельными кнопками.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(
            "Рада снова тебя видеть! Анкета на месте, можно сразу в ленту.\n"
            "Если хочешь обновить профиль, жми 'Редактировать анкету'.",
            reply_markup=main_menu_keyboard(),
        )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "VibeDate Bot - мини-гид\n\n"
        "Главное:\n"
        "/start - регистрация или вход\n"
        "/profile_wizard - заполнить анкету шаг за шагом\n"
        "/edit_profile - точечно редактировать поля\n"
        "/add_photo - добавить фото (до 5)\n"
        "/my_photos - посмотреть, сколько фото загружено\n"
        "/where - где что менять в боте\n"
        "/my_profile - показать анкету\n"
        "/feed - следующая анкета\n"
        "/like <profile_id> и /skip <profile_id>\n\n"
        "Быстрое редактирование:\n"
        "/set_name Аня\n"
        "/set_age 22\n"
        "/set_gender м|ж\n"
        "/set_city Москва\n"
        "/set_interests музыка,спорт\n"
        "/set_bio Текст о себе\n"
        "/set_looking_for м|ж|м,ж\n"
        "/set_range 18 30\n\n"
        "Важно: контакт собеседника раскрывается только после взаимного лайка.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("where"))
async def cmd_where(message: Message) -> None:
    await message.answer(
        "Коротко:\n"
        "- 'Редактировать анкету' или /edit_profile - поменять отдельные поля\n"
        "- 'Добавить фото' или /add_photo - загрузить фото (до 5)\n"
        "- /my_photos - посмотреть количество фото\n"
        "- 'Лента анкет' или /feed - смотреть новые анкеты"
    )
