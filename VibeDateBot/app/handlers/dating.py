from __future__ import annotations

import html
import logging

import asyncpg
from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.db import (
    add_profile_photo_by_tg_id,
    ensure_user_and_profile,
    get_next_candidate,
    get_profile_photos_by_tg_id,
    get_profile_by_tg_id,
    react_to_candidate,
    update_profile_field,
)
from app.keyboards.main import candidate_actions_keyboard, edit_profile_keyboard
from app.services.profile import refresh_profile_rating

router = Router()
logger = logging.getLogger(__name__)

MIN_USER_AGE = 18
MAX_USER_AGE = 100
MIN_SEARCH_AGE = 18
MAX_SEARCH_AGE = 100


class ProfileWizard(StatesGroup):
    display_name = State()
    age = State()
    gender = State()
    city = State()
    interests = State()
    bio = State()
    looking_for = State()
    min_age = State()
    max_age = State()


class EditProfileField(StatesGroup):
    value = State()


class PhotoUpload(StatesGroup):
    waiting = State()


def _normalize_gender(value: str) -> str | None:
    text = value.strip().lower()
    if text in {"м", "m"}:
        return "m"
    if text in {"ж", "f"}:
        return "f"
    return None


def _normalize_looking_for(value: str) -> str | None:
    tokens = value.lower().replace(" и ", ",").replace("/", ",").replace(" ", ",")
    genders: set[str] = set()
    for token in [part.strip() for part in tokens.split(",") if part.strip()]:
        normalized = _normalize_gender(token)
        if normalized is None:
            return None
        genders.add(normalized)
    if not genders:
        return None
    if len(genders) == 2:
        return "a"
    return next(iter(genders))


def _display_gender(value: object) -> str:
    if value == "m":
        return "м"
    if value == "f":
        return "ж"
    if value in (None, ""):
        return "не указано"
    return str(value)


def _display_looking_for(value: object) -> str:
    if value == "a":
        return "м и ж"
    return _display_gender(value)


def _command_text(message: Message) -> str:
    return (message.text or "").strip()


def _arg_after_command(message: Message) -> str:
    text = _command_text(message)
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _profile_text(profile: dict[str, object]) -> str:
    username = profile.get("username")
    username_text = f"@{username}" if username else "не указан"
    return (
        f"Имя: {profile.get('display_name') or 'не указано'}\n"
        f"Username: {username_text}\n"
        f"Возраст: {profile['age']}\n"
        f"Пол: {_display_gender(profile['gender'])}\n"
        f"Город: {profile['city']}\n"
        f"Интересы: {profile['interests']}\n"
        f"О себе: {profile['bio']}\n"
        f"Ищу: {_display_looking_for(profile['looking_for'])}\n"
        f"Диапазон возраста: {profile['min_age']} - {profile['max_age']}\n"
        f"Первичный рейтинг: {profile['primary_rating']}\n"
        f"Заполненность анкеты: {profile['completeness_score']}%"
    )


def _profile_ready(profile: dict[str, object]) -> bool:
    required = (
        "display_name",
        "age",
        "gender",
        "city",
        "interests",
        "bio",
        "looking_for",
        "min_age",
        "max_age",
    )
    return all(profile.get(key) not in (None, "") for key in required)


def _match_contact_line(contact: dict[str, object] | None) -> str:
    if not contact:
        return "контакт недоступен"
    display_name = html.escape(str(contact.get("display_name") or "Пользователь"))
    username = str(contact.get("username") or "").strip()
    tg_id = contact.get("tg_id")
    if username:
        return f"{display_name} (@{html.escape(username)})"
    if tg_id is not None:
        return f'{display_name} (<a href="tg://user?id={tg_id}">написать в Telegram</a>)'
    return display_name


async def _ensure_profile_exists(
    db_pool: asyncpg.Pool,
    user_tg_id: int,
    username: str | None,
) -> dict[str, object] | None:
    profile = await get_profile_by_tg_id(db_pool, user_tg_id)
    if profile is not None:
        return profile
    await ensure_user_and_profile(db_pool, user_tg_id, username)
    return await get_profile_by_tg_id(db_pool, user_tg_id)


async def _show_feed(
    message: Message,
    db_pool: asyncpg.Pool,
    viewer_tg_id: int | None = None,
    viewer_username: str | None = None,
) -> None:
    if viewer_tg_id is None and message.from_user is None:
        return
    user_tg_id = viewer_tg_id if viewer_tg_id is not None else int(message.from_user.id)
    username = viewer_username if viewer_tg_id is not None else message.from_user.username
    profile = await _ensure_profile_exists(db_pool, user_tg_id, username)
    if profile is None:
        await message.answer("Не получилось открыть анкету. Попробуй /start чуть позже.")
        return
    if not _profile_ready(profile):
        await message.answer(
            "Перед лентой нужно оформить профиль полностью. Жми 'Заполнить анкету' - это займет пару минут."
        )
        return
    candidate = await get_next_candidate(db_pool, user_tg_id)
    if candidate is None:
        await message.answer("Похоже, анкеты закончились. Загляни чуть позже - лента обновится.")
        return
    await message.answer(
        "Новая анкета:\n"
        f"Имя: {candidate.get('display_name') or 'не указано'}\n"
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
    bot: Bot,
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
        contacts = result.get("match_contacts") or {}
        from_user = contacts.get("from_user")
        to_user = contacts.get("to_user")
        if from_user and to_user:
            from_text = (
                "Взаимный лайк! У вас мэтч.\n"
                f"Контакт собеседника: {_match_contact_line(to_user)}"
            )
            to_text = (
                "Взаимный лайк! У вас мэтч.\n"
                f"Контакт собеседника: {_match_contact_line(from_user)}"
            )
            try:
                await bot.send_message(int(from_user["tg_id"]), from_text, parse_mode="HTML")
                await bot.send_message(int(to_user["tg_id"]), to_text, parse_mode="HTML")
            except Exception:
                logger.exception("Failed to deliver match contacts")
                return True, "Взаимный лайк! Контакты готовы, но не удалось отправить уведомление."
        return True, "Взаимный лайк! Контакты отправлены вам обоим."
    return True, "Принято! Смотрим следующую анкету."


@router.message(Command("my_profile"))
async def cmd_my_profile(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    profile = await _ensure_profile_exists(db_pool, message.from_user.id, message.from_user.username)
    if profile is None:
        await message.answer("Не удалось загрузить анкету. Попробуй /start.")
        return
    await message.answer(_profile_text(profile))
    await message.answer(
        "Обновить данные можно кнопкой 'Редактировать анкету'. "
        "Фото добавляются кнопкой 'Добавить фото'."
    )


@router.message(Command("edit_profile"))
@router.message(lambda m: (m.text or "").strip() == "Редактировать анкету")
async def cmd_edit_profile(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    profile = await _ensure_profile_exists(db_pool, message.from_user.id, message.from_user.username)
    if profile is None:
        await message.answer("Не получилось открыть редактор анкеты. Попробуй /start.")
        return
    await message.answer(
        "Что меняем в анкете? Выбери поле ниже:",
        reply_markup=edit_profile_keyboard(),
    )


@router.callback_query(lambda c: c.data is not None and c.data.startswith("edit:"))
async def cb_edit_profile(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data is None or callback.message is None:
        return
    field = callback.data.split(":", maxsplit=1)[1]
    prompts = {
        "display_name": "Введи новое имя (2-40 символов):",
        "age": f"Введи новый возраст ({MIN_USER_AGE}-{MAX_USER_AGE}):",
        "city": "Введи новый город:",
        "interests": "Введи интересы через запятую:",
        "bio": "Напиши новый текст 'о себе':",
        "looking_for": "Кого ищешь? Варианты: м, ж или м,ж",
        "range": f"Введи диапазон двумя числами: {MIN_SEARCH_AGE} {MAX_SEARCH_AGE}",
    }
    if field not in prompts:
        await callback.answer("Неизвестное поле", show_alert=True)
        return
    await state.set_state(EditProfileField.value)
    await state.update_data(edit_field=field)
    await callback.answer()
    await callback.message.answer(prompts[field])


@router.message(EditProfileField.value)
async def edit_profile_value(message: Message, state: FSMContext, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    text = (message.text or "").strip()
    data = await state.get_data()
    field = data.get("edit_field")
    if not field:
        await state.clear()
        await message.answer("Редактирование сбилось, открой его снова.")
        return

    update_values: list[tuple[str, object]] = []
    if field == "display_name":
        if len(text) < 2 or len(text) > 40:
            await message.answer("Имя должно быть длиной 2-40 символов.")
            return
        update_values.append(("display_name", text))
    elif field == "age":
        if not text.isdigit():
            await message.answer("Возраст должен быть числом.")
            return
        age = int(text)
        if age < MIN_USER_AGE or age > MAX_USER_AGE:
            await message.answer(f"Возраст должен быть в диапазоне {MIN_USER_AGE}-{MAX_USER_AGE}.")
            return
        update_values.append(("age", age))
    elif field == "city":
        if not text:
            await message.answer("Город не может быть пустым.")
            return
        update_values.append(("city", text))
    elif field == "interests":
        if not text:
            await message.answer("Интересы не могут быть пустыми.")
            return
        update_values.append(("interests", text))
    elif field == "bio":
        if len(text) < 10:
            await message.answer("О себе лучше написать чуть подробнее (хотя бы 10 символов).")
            return
        update_values.append(("bio", text))
    elif field == "looking_for":
        normalized = _normalize_looking_for(text)
        if normalized is None:
            await message.answer("Формат: м, ж или м,ж.")
            return
        update_values.append(("looking_for", normalized))
    elif field == "range":
        parts = text.split()
        if len(parts) != 2 or (not parts[0].isdigit()) or (not parts[1].isdigit()):
            await message.answer("Формат диапазона: 18 30")
            return
        min_age, max_age = int(parts[0]), int(parts[1])
        if min_age < MIN_SEARCH_AGE or max_age > MAX_SEARCH_AGE or min_age > max_age:
            await message.answer(f"Корректный диапазон: {MIN_SEARCH_AGE}-{MAX_SEARCH_AGE}, min <= max.")
            return
        update_values.append(("min_age", min_age))
        update_values.append(("max_age", max_age))
    else:
        await message.answer("Это поле пока нельзя редактировать.")
        return

    profile_id: int | None = None
    for target_field, value in update_values:
        row = await update_profile_field(db_pool, message.from_user.id, target_field, value)
        if row is None:
            await state.clear()
            await message.answer("Профиль не найден. Нажми /start.")
            return
        profile_id = int(row["id"])
    if profile_id is not None:
        await refresh_profile_rating(db_pool, profile_id)
    await state.clear()
    await message.answer("Готово, обновление сохранено.")


@router.message(Command("add_photo"))
@router.message(lambda m: (m.text or "").strip() == "Добавить фото")
async def cmd_add_photo(message: Message, state: FSMContext) -> None:
    await state.set_state(PhotoUpload.waiting)
    await message.answer(
        "Пришли фото одним сообщением. Можно хранить до 5 фото, первое будет главным."
    )


@router.message(Command("my_photos"))
async def cmd_my_photos(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    photos = await get_profile_photos_by_tg_id(db_pool, message.from_user.id)
    if not photos:
        await message.answer("Фотографий пока нет. Добавь через 'Добавить фото' или /add_photo.")
        return
    await message.answer(f"У тебя {len(photos)} фото в анкете.")


@router.message(PhotoUpload.waiting, lambda m: bool(m.photo))
async def upload_photo(message: Message, state: FSMContext, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None or not message.photo:
        return
    file_id = message.photo[-1].file_id
    result = await add_profile_photo_by_tg_id(db_pool, message.from_user.id, file_id)
    if result is None:
        await state.clear()
        await message.answer("Сначала создай профиль командой /start.")
        return
    if not result["saved"]:
        await state.clear()
        await message.answer("Лимит фото достигнут: максимум 5. Скоро добавлю удаление фото.")
        return
    await refresh_profile_rating(db_pool, int(result["profile_id"]))
    await state.clear()
    await message.answer(f"Фото сохранено! Теперь в анкете {result['photo_count']} фото.")


@router.message(PhotoUpload.waiting)
async def upload_photo_fallback(message: Message) -> None:
    await message.answer("Жду именно фото. Отправь картинку, пожалуйста.")


@router.message(Command("set_name"))
async def cmd_set_name(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    arg = _arg_after_command(message)
    if len(arg) < 2 or len(arg) > 40:
        await message.answer("Использование: /set_name Аня (2-40 символов)")
        return
    row = await update_profile_field(db_pool, message.from_user.id, "display_name", arg)
    if row is None:
        await message.answer("Профиль не найден. Сначала /start")
        return
    await refresh_profile_rating(db_pool, row["id"])
    await message.answer("Имя в анкете обновлено.")


@router.message(Command("set_age"))
async def cmd_set_age(message: Message, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    arg = _arg_after_command(message)
    if not arg.isdigit():
        await message.answer("Использование: /set_age 22")
        return
    age = int(arg)
    if age < MIN_USER_AGE or age > MAX_USER_AGE:
        await message.answer(f"Возраст должен быть от {MIN_USER_AGE} до {MAX_USER_AGE}.")
        return
    row = await update_profile_field(db_pool, message.from_user.id, "age", age)
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
    arg = _normalize_looking_for(_arg_after_command(message))
    if arg is None:
        await message.answer("Использование: /set_looking_for м|ж|м,ж")
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
    if min_age < MIN_SEARCH_AGE or max_age > MAX_SEARCH_AGE:
        await message.answer(f"Диапазон поиска должен быть в пределах {MIN_SEARCH_AGE}-{MAX_SEARCH_AGE}.")
        return
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


async def _react(message: Message, db_pool: asyncpg.Pool, is_like: bool, bot: Bot) -> None:
    if message.from_user is None:
        return
    profile = await _ensure_profile_exists(db_pool, message.from_user.id, message.from_user.username)
    if profile is None:
        await message.answer("Не вижу твой профиль. Нажми /start.")
        return
    if not _profile_ready(profile):
        await message.answer("Сначала заверши анкету, потом можно ставить лайки.")
        return
    arg = _arg_after_command(message)
    if not arg.isdigit():
        await message.answer("Укажи ID анкеты: /like 7 или /skip 7")
        return
    profile_id = int(arg)
    ok, text = await _react_and_reply(message.from_user.id, profile_id, is_like, db_pool, bot)
    await message.answer(text)
    if ok:
        await _show_feed(message, db_pool)


@router.message(Command("like"))
async def cmd_like(message: Message, db_pool: asyncpg.Pool, bot: Bot) -> None:
    await _react(message, db_pool, is_like=True, bot=bot)


@router.message(Command("skip"))
async def cmd_skip(message: Message, db_pool: asyncpg.Pool, bot: Bot) -> None:
    await _react(message, db_pool, is_like=False, bot=bot)


@router.callback_query(lambda c: c.data is not None and (c.data.startswith("like:") or c.data.startswith("skip:")))
async def cb_reaction(callback: CallbackQuery, db_pool: asyncpg.Pool, bot: Bot) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        return
    parts = callback.data.split(":", maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await callback.answer("Некорректная команда", show_alert=True)
        return
    is_like = parts[0] == "like"
    profile_id = int(parts[1])
    profile = await _ensure_profile_exists(
        db_pool,
        callback.from_user.id,
        callback.from_user.username,
    )
    if profile is None:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    if not _profile_ready(profile):
        await callback.answer("Сначала заполни анкету", show_alert=True)
        return
    ok, text = await _react_and_reply(callback.from_user.id, profile_id, is_like, db_pool, bot)
    await callback.answer()
    await callback.message.answer(text)
    if ok:
        await _show_feed(
            callback.message,
            db_pool,
            viewer_tg_id=callback.from_user.id,
            viewer_username=callback.from_user.username,
        )


@router.message(Command("profile_wizard"))
@router.message(lambda m: (m.text or "").strip() == "Заполнить анкету")
async def cmd_profile_wizard(message: Message, state: FSMContext) -> None:
    await state.set_state(ProfileWizard.display_name)
    await message.answer("Шаг 1/9. Введи имя для анкеты (2-40 символов):")


@router.message(ProfileWizard.display_name)
async def wizard_display_name(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2 or len(text) > 40:
        await message.answer("Имя должно быть от 2 до 40 символов. Попробуй еще раз:")
        return
    await state.update_data(display_name=text)
    await state.set_state(ProfileWizard.age)
    await message.answer("Шаг 2/9. Введи возраст (например 22):")


@router.message(ProfileWizard.age)
async def wizard_age(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Возраст должен быть числом. Попробуй еще раз:")
        return
    age = int(text)
    if age < MIN_USER_AGE or age > MAX_USER_AGE:
        await message.answer(f"Возраст должен быть от {MIN_USER_AGE} до {MAX_USER_AGE}:")
        return
    await state.update_data(age=age)
    await state.set_state(ProfileWizard.gender)
    await message.answer("Шаг 3/9. Пол (м/ж):")


@router.message(ProfileWizard.gender)
async def wizard_gender(message: Message, state: FSMContext) -> None:
    normalized = _normalize_gender((message.text or "").strip())
    if normalized is None:
        await message.answer("Введи м или ж:")
        return
    await state.update_data(gender=normalized)
    await state.set_state(ProfileWizard.city)
    await message.answer("Шаг 4/9. Город:")


@router.message(ProfileWizard.city)
async def wizard_city(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Город не должен быть пустым:")
        return
    await state.update_data(city=text)
    await state.set_state(ProfileWizard.interests)
    await message.answer("Шаг 5/9. Интересы (через запятую):")


@router.message(ProfileWizard.interests)
async def wizard_interests(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Интересы не должны быть пустыми:")
        return
    await state.update_data(interests=text)
    await state.set_state(ProfileWizard.bio)
    await message.answer("Шаг 6/9. Коротко о себе:")


@router.message(ProfileWizard.bio)
async def wizard_bio(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Bio не должно быть пустым:")
        return
    await state.update_data(bio=text)
    await state.set_state(ProfileWizard.looking_for)
    await message.answer("Шаг 7/9. Кого ищешь (м/ж или м,ж):")


@router.message(ProfileWizard.looking_for)
async def wizard_looking_for(message: Message, state: FSMContext) -> None:
    normalized = _normalize_looking_for((message.text or "").strip())
    if normalized is None:
        await message.answer("Введи м, ж или м,ж:")
        return
    await state.update_data(looking_for=normalized)
    await state.set_state(ProfileWizard.min_age)
    await message.answer("Шаг 8/9. Минимальный возраст поиска:")


@router.message(ProfileWizard.min_age)
async def wizard_min_age(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Минимальный возраст должен быть числом:")
        return
    min_age = int(text)
    if min_age < MIN_SEARCH_AGE or min_age > MAX_SEARCH_AGE:
        await message.answer(f"Минимальный возраст должен быть в диапазоне {MIN_SEARCH_AGE}-{MAX_SEARCH_AGE}:")
        return
    await state.update_data(min_age=min_age)
    await state.set_state(ProfileWizard.max_age)
    await message.answer("Шаг 9/9. Максимальный возраст поиска:")


@router.message(ProfileWizard.max_age)
async def wizard_max_age(message: Message, state: FSMContext, db_pool: asyncpg.Pool) -> None:
    if message.from_user is None:
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Максимальный возраст должен быть числом:")
        return
    max_age = int(text)
    if max_age < MIN_SEARCH_AGE or max_age > MAX_SEARCH_AGE:
        await message.answer(f"Максимальный возраст должен быть в диапазоне {MIN_SEARCH_AGE}-{MAX_SEARCH_AGE}:")
        return
    data = await state.get_data()
    min_age = int(data["min_age"])
    if max_age < min_age:
        await message.answer("Максимальный возраст должен быть >= минимального. Введи снова:")
        return

    updates = {
        "display_name": data["display_name"],
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
