from __future__ import annotations

import logging

import asyncpg
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.db import (
    get_next_candidate,
    get_profile_by_tg_id,
    react_to_candidate,
    update_profile_field,
)
from app.keyboards.main import candidate_actions_keyboard
from app.services.profile import refresh_profile_rating

router = Router()
logger = logging.getLogger(__name__)


class ProfileWizard(StatesGroup):
    age = State()
    gender = State()
    city = State()
    interests = State()
    bio = State()
    looking_for = State()
    min_age = State()
    max_age = State()


def _normalize_gender(value: str) -> str | None:
    text = value.strip().lower()
    if text in {"м", "m"}:
        return "m"
    if text in {"ж", "f"}:
        return "f"
    return None


def _display_gender(value: object) -> str:
    if value == "m":
        return "м"
    if value == "f":
        return "ж"
    return str(value)


def _command_text(message: Message) -> str:
    return (message.text or "").strip()


def _arg_after_command(message: Message) -> str:
    text = _command_text(message)
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _profile_text(profile: dict[str, object]) -> str:
    return (
        f"ID анкеты: {profile['id']}\n"
        f"Возраст: {profile['age']}\n"
        f"Пол: {_display_gender(profile['gender'])}\n"
        f"Город: {profile['city']}\n"
        f"Интересы: {profile['interests']}\n"
        f"О себе: {profile['bio']}\n"
        f"Ищу: {_display_gender(profile['looking_for'])}\n"
        f"Диапазон возраста: {profile['min_age']} - {profile['max_age']}\n"
        f"Первичный рейтинг: {profile['primary_rating']}\n"
        f"Заполненность анкеты: {profile['completeness_score']}%"
    )


async def _show_feed(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    candidate = await get_next_candidate(db_pool, message.from_user.id)
    if candidate is None:
        await message.answer("Новых анкет пока нет. Попробуй позже.")
        return
    await message.answer(
        f"Анкета #{candidate['profile_id']}\n"
        f"@{candidate['username'] or 'no_username'}\n"
        f"Возраст: {candidate['age']}\n"
        f"Пол: {_display_gender(candidate['gender'])}\n"
        f"Город: {candidate['city']}\n"
        f"Интересы: {candidate['interests']}\n"
        f"О себе: {candidate['bio']}\n"
        f"Рейтинг: {candidate['combined_rating']}",
        reply_markup=candidate_actions_keyboard(candidate["profile_id"]),
    )


async def _react_and_reply(
    user_tg_id: int,
    profile_id: int,
    is_like: bool,
    db_pool: asyncpg.Pool,
) -> tuple[bool, str]:
    try:
        result = await react_to_candidate(
            pool=db_pool,
            from_tg_id=user_tg_id,
            to_profile_id=profile_id,
            is_like=is_like,
        )
        await refresh_profile_rating(db_pool, result["to_profile_id"])
        await refresh_profile_rating(db_pool, result["from_profile_id"])
    except Exception:
        logger.exception("Reaction failed from tg_id=%s", user_tg_id)
        return False, "Не удалось сохранить реакцию."
    if result["is_match"]:
        return True, "Взаимный лайк! У вас мэтч."
    return True, "Реакция сохранена."


@router.message(Command("my_profile"))
async def cmd_my_profile(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    profile = await get_profile_by_tg_id(db_pool, message.from_user.id)
    if profile is None:
        await message.answer("Профиль не найден. Сначала отправь /start")
        return
    await message.answer(_profile_text(profile))


@router.message(Command("set_age"))
async def cmd_set_age(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    arg = _arg_after_command(message)
    if not arg.isdigit():
        await message.answer("Использование: /set_age 22")
        return
    row = await update_profile_field(db_pool, message.from_user.id, "age", int(arg))
    if row is None:
        await message.answer("Профиль не найден. Сначала /start")
        return
    await refresh_profile_rating(db_pool, row["id"])
    await message.answer("Возраст обновлен.")


@router.message(Command("set_gender"))
async def cmd_set_gender(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    arg = _normalize_gender(_arg_after_command(message))
    if arg is None:
        await message.answer("Использование: /set_gender м|ж")
        return
    row = await update_profile_field(db_pool, message.from_user.id, "gender", arg)
    if row is None:
        await message.answer("Профиль не найден. Сначала /start")
        return
    await refresh_profile_rating(db_pool, row["id"])
    await message.answer("Пол обновлен.")


@router.message(Command("set_city"))
async def cmd_set_city(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    arg = _arg_after_command(message)
    if not arg:
        await message.answer("Использование: /set_city Moscow")
        return
    row = await update_profile_field(db_pool, message.from_user.id, "city", arg)
    if row is None:
        await message.answer("Профиль не найден. Сначала /start")
        return
    await refresh_profile_rating(db_pool, row["id"])
    await message.answer("Город обновлен.")


@router.message(Command("set_interests"))
async def cmd_set_interests(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    arg = _arg_after_command(message)
    if not arg:
        await message.answer("Использование: /set_interests music,films,sport")
        return
    row = await update_profile_field(db_pool, message.from_user.id, "interests", arg)
    if row is None:
        await message.answer("Профиль не найден. Сначала /start")
        return
    await refresh_profile_rating(db_pool, row["id"])
    await message.answer("Интересы обновлены.")


@router.message(Command("set_bio"))
async def cmd_set_bio(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    arg = _arg_after_command(message)
    if not arg:
        await message.answer("Использование: /set_bio Текст о себе")
        return
    row = await update_profile_field(db_pool, message.from_user.id, "bio", arg)
    if row is None:
        await message.answer("Профиль не найден. Сначала /start")
        return
    await refresh_profile_rating(db_pool, row["id"])
    await message.answer("Bio обновлено.")


@router.message(Command("set_looking_for"))
async def cmd_set_looking_for(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    arg = _normalize_gender(_arg_after_command(message))
    if arg is None:
        await message.answer("Использование: /set_looking_for м|ж")
        return
    row = await update_profile_field(db_pool, message.from_user.id, "looking_for", arg)
    if row is None:
        await message.answer("Профиль не найден. Сначала /start")
        return
    await refresh_profile_rating(db_pool, row["id"])
    await message.answer("Предпочтение обновлено.")


@router.message(Command("set_range"))
async def cmd_set_range(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    arg = _arg_after_command(message)
    parts = arg.split()
    if len(parts) != 2 or (not parts[0].isdigit()) or (not parts[1].isdigit()):
        await message.answer("Использование: /set_range 18 30")
        return
    min_age, max_age = int(parts[0]), int(parts[1])
    if min_age > max_age:
        await message.answer("Неверный диапазон: min_age > max_age")
        return
    row = await update_profile_field(db_pool, message.from_user.id, "min_age", min_age)
    if row is None:
        await message.answer("Профиль не найден. Сначала /start")
        return
    await update_profile_field(db_pool, message.from_user.id, "max_age", max_age)
    await refresh_profile_rating(db_pool, row["id"])
    await message.answer("Возрастной диапазон обновлен.")


@router.message(Command("feed"))
async def cmd_feed(message: Message, db_pool: asyncpg.Pool) -> None:
    await _show_feed(message, db_pool)


async def _react(message: Message, db_pool: asyncpg.Pool, is_like: bool) -> None:
    if message.from_user is None:
        return
    arg = _arg_after_command(message)
    if not arg.isdigit():
        await message.answer("Укажи ID анкеты: /like 7 или /skip 7")
        return
    profile_id = int(arg)
    ok, text = await _react_and_reply(message.from_user.id, profile_id, is_like, db_pool)
    await message.answer(text)
    if ok:
        await _show_feed(message, db_pool)


@router.message(Command("like"))
async def cmd_like(message: Message, db_pool: asyncpg.Pool) -> None:
    await _react(message, db_pool, is_like=True)


@router.message(Command("skip"))
async def cmd_skip(message: Message, db_pool: asyncpg.Pool) -> None:
    await _react(message, db_pool, is_like=False)


@router.callback_query(lambda c: c.data is not None and (c.data.startswith("like:") or c.data.startswith("skip:")))
async def cb_reaction(callback: CallbackQuery, db_pool: asyncpg.Pool) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        return
    parts = callback.data.split(":", maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await callback.answer("Некорректная команда", show_alert=True)
        return
    is_like = parts[0] == "like"
    profile_id = int(parts[1])
    ok, text = await _react_and_reply(callback.from_user.id, profile_id, is_like, db_pool)
    await callback.answer()
    await callback.message.answer(text)
    if ok:
        await _show_feed(callback.message, db_pool)


@router.message(Command("profile_wizard"))
@router.message(lambda m: (m.text or "").strip() == "Заполнить анкету")
async def cmd_profile_wizard(message: Message, state: FSMContext) -> None:
    await state.set_state(ProfileWizard.age)
    await message.answer("Шаг 1/8. Введи возраст (например 22):")


@router.message(ProfileWizard.age)
async def wizard_age(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Возраст должен быть числом. Попробуй еще раз:")
        return
    await state.update_data(age=int(text))
    await state.set_state(ProfileWizard.gender)
    await message.answer("Шаг 2/8. Пол (м/ж):")


@router.message(ProfileWizard.gender)
async def wizard_gender(message: Message, state: FSMContext) -> None:
    normalized = _normalize_gender((message.text or "").strip())
    if normalized is None:
        await message.answer("Введи м или ж:")
        return
    await state.update_data(gender=normalized)
    await state.set_state(ProfileWizard.city)
    await message.answer("Шаг 3/8. Город:")


@router.message(ProfileWizard.city)
async def wizard_city(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Город не должен быть пустым:")
        return
    await state.update_data(city=text)
    await state.set_state(ProfileWizard.interests)
    await message.answer("Шаг 4/8. Интересы (через запятую):")


@router.message(ProfileWizard.interests)
async def wizard_interests(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Интересы не должны быть пустыми:")
        return
    await state.update_data(interests=text)
    await state.set_state(ProfileWizard.bio)
    await message.answer("Шаг 5/8. Коротко о себе:")


@router.message(ProfileWizard.bio)
async def wizard_bio(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Bio не должно быть пустым:")
        return
    await state.update_data(bio=text)
    await state.set_state(ProfileWizard.looking_for)
    await message.answer("Шаг 6/8. Кого ищешь (м/ж):")


@router.message(ProfileWizard.looking_for)
async def wizard_looking_for(message: Message, state: FSMContext) -> None:
    normalized = _normalize_gender((message.text or "").strip())
    if normalized is None:
        await message.answer("Введи м или ж:")
        return
    await state.update_data(looking_for=normalized)
    await state.set_state(ProfileWizard.min_age)
    await message.answer("Шаг 7/8. Минимальный возраст:")


@router.message(ProfileWizard.min_age)
async def wizard_min_age(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Минимальный возраст должен быть числом:")
        return
    await state.update_data(min_age=int(text))
    await state.set_state(ProfileWizard.max_age)
    await message.answer("Шаг 8/8. Максимальный возраст:")


@router.message(ProfileWizard.max_age)
async def wizard_max_age(message: Message, state: FSMContext, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Максимальный возраст должен быть числом:")
        return
    max_age = int(text)
    data = await state.get_data()
    min_age = int(data["min_age"])
    if max_age < min_age:
        await message.answer("Максимальный возраст должен быть >= минимального. Введи снова:")
        return

    updates = {
        "age": data["age"],
        "gender": data["gender"],
        "city": data["city"],
        "interests": data["interests"],
        "bio": data["bio"],
        "looking_for": data["looking_for"],
        "min_age": min_age,
        "max_age": max_age,
    }
    profile_id: int | None = None
    for field, value in updates.items():
        row = await update_profile_field(db_pool, message.from_user.id, field, value)
        if row is None:
            await state.clear()
            await message.answer("Профиль не найден. Сначала отправь /start")
            return
        profile_id = row["id"]

    if profile_id is not None:
        await refresh_profile_rating(db_pool, profile_id)
    await state.clear()
    await message.answer("Анкета сохранена. Используй кнопку 'Лента анкет' или команду /feed")


@router.message(lambda m: (m.text or "").strip() == "Моя анкета")
async def btn_my_profile(message: Message, db_pool: asyncpg.Pool) -> None:
    await cmd_my_profile(message, db_pool)


@router.message(lambda m: (m.text or "").strip() == "Лента анкет")
async def btn_feed(message: Message, db_pool: asyncpg.Pool) -> None:
    await _show_feed(message, db_pool)
