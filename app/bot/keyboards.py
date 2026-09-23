from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.models import Unit


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Найти жильё")]],
        resize_keyboard=True,
    )


def units_keyboard(units: list[Unit]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{u.title} — {u.price_per_night} ₽", callback_data=f"unit:{u.id}")]
        for u in units
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
