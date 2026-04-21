from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Моя анкета"), KeyboardButton(text="Заполнить анкету")],
            [KeyboardButton(text="Лента анкет")],
        ],
        resize_keyboard=True,
    )


def candidate_actions_keyboard(profile_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Лайк", callback_data=f"like:{profile_id}")
    builder.button(text="Скип", callback_data=f"skip:{profile_id}")
    builder.adjust(2)
    return builder.as_markup()
