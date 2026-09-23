from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.models import Unit


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Найти жильё")]],
        resize_keyboard=True,
    )


def units_keyboard(units: list[Unit]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{u.title} — {u.price_per_night} ₽", callback_data=f"unit:{u.id}"
            )
        ]
        for u in units
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def booking_decision_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить", callback_data=f"booking:confirm:{booking_id}"
                ),
                InlineKeyboardButton(
                    text="Отклонить", callback_data=f"booking:decline:{booking_id}"
                ),
            ]
        ]
    )
