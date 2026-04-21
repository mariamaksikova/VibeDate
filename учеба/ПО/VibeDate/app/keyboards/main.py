from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Моя анкета"), KeyboardButton(text="Заполнить анкету")],
            [KeyboardButton(text="Редактировать анкету"), KeyboardButton(text="Добавить фото")],
            [KeyboardButton(text="Лента анкет"), KeyboardButton(text="Отмена заполнения")],
        ],
        resize_keyboard=True,
    )


def candidate_actions_keyboard(profile_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Лайк", callback_data=f"like:{profile_id}")
    builder.button(text="Скип", callback_data=f"skip:{profile_id}")
    builder.adjust(2)
    return builder.as_markup()


def edit_profile_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Имя", callback_data="edit:display_name")
    builder.button(text="Возраст", callback_data="edit:age")
    builder.button(text="Город", callback_data="edit:city")
    builder.button(text="Интересы", callback_data="edit:interests")
    builder.button(text="О себе", callback_data="edit:bio")
    builder.button(text="Ищу (м/ж/м,ж)", callback_data="edit:looking_for")
    builder.button(text="Диапазон возраста", callback_data="edit:range")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()
