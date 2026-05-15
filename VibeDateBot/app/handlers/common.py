from __future__ import annotations

import logging

import asyncpg
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from app.db import ensure_user_and_profile, get_profile_by_tg_id
from app.keyboards.main import main_menu_keyboard

router = Router()
logger = logging.getLogger(__name__)


def _referral_code_from_start(message: Message) -> str | None:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    arg = parts[1].strip()
    if arg.startswith("ref_"):
        return arg[4:]
    return arg[:20] if arg else None


@router.message(CommandStart())
async def cmd_start(message: Message, db_pool: asyncpg.Pool, bot) -> None:
    if message.from_user is None:
        return

    ref_code = _referral_code_from_start(message)
    try:
        is_new, info = await ensure_user_and_profile(
            pool=db_pool,
            tg_id=message.from_user.id,
            username=message.from_user.username,
            referral_code_from_start=ref_code,
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
        extra = ""
        if ref_code:
            extra = "\nРеферальный код друга учтён — спасибо!"
        await message.answer(
            "Привет! Добро пожаловать в VibeDate 💜\n"
            "Соберем классную анкету? Жми 'Заполнить анкету'.\n"
            "Потом можно точечно редактировать поля и докидывать фото."
            f"{extra}",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(
            "С возвращением! Анкета на месте, можно сразу в ленту 🔥\n"
            "Если хочешь освежить профиль, жми 'Редактировать анкету'.",
            reply_markup=main_menu_keyboard(),
        )


@router.message(Command("invite"))
async def cmd_invite(message: Message, db_pool: asyncpg.Pool, bot) -> None:
    if message.from_user is None:
        return
    profile = await get_profile_by_tg_id(db_pool, message.from_user.id)
    if profile is None:
        await message.answer("Сначала /start")
        return
    code = profile.get("referral_code")
    if not code:
        await message.answer("Реферальный код ещё не создан. Нажми /start.")
        return
    me = await bot.get_me()
    username = me.username or "Vibe_DateBot"
    link = f"https://t.me/{username}?start=ref_{code}"
    await message.answer(
        "Пригласи друга — это повышает комбинированный рейтинг:\n"
        f"{link}\n\n"
        "Друг должен перейти по ссылке и нажать Start."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "VibeDate Bot - мини-гид\n\n"
        "Главное:\n"
        "/start - регистрация или вход\n"
        "/invite - реферальная ссылка\n"
        "/profile_wizard - заполнить анкету шаг за шагом\n"
        "/edit_profile - точечно редактировать поля\n"
        "/add_photo - добавить фото в MinIO (до 5)\n"
        "/my_photos - посмотреть, сколько фото загружено\n"
        "/cancel - выйти из заполнения/редактирования\n"
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
