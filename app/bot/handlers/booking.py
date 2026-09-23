from datetime import date, datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import main_menu, units_keyboard
from app.bot.states import BookingFSM
from app.db import SessionLocal
from app.services.booking import create_booking, list_available_units

router = Router()


def _parse_ru_date(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


@router.message(BookingFSM.check_in)
async def got_check_in(message: Message, state: FSMContext) -> None:
    d = _parse_ru_date(message.text or "")
    if d is None or d < date.today():
        await message.answer("Непонятная дата. Нужен формат ДД.ММ.ГГГГ (не раньше сегодня).")
        return
    await state.update_data(check_in=d.isoformat())
    await state.set_state(BookingFSM.check_out)
    await message.answer("Введите дату выезда (ДД.ММ.ГГГГ):")


@router.message(BookingFSM.check_out)
async def got_check_out(message: Message, state: FSMContext, owner_id: int) -> None:
    d = _parse_ru_date(message.text or "")
    data = await state.get_data()
    check_in = date.fromisoformat(data["check_in"])
    if d is None or d <= check_in:
        await message.answer("Дата выезда должна быть позже заезда. Формат ДД.ММ.ГГГГ.")
        return

    await state.update_data(check_out=d.isoformat())
    async with SessionLocal() as session:
        units = await list_available_units(session, owner_id, check_in, d)

    if not units:
        await state.clear()
        await message.answer(
            "На эти даты свободных вариантов нет. Попробуйте другие даты.",
            reply_markup=main_menu(),
        )
        return

    await state.set_state(BookingFSM.choose_unit)
    lines = ["Свободно на ваши даты:\n"]
    for u in units:
        lines.append(f"• <b>{u.title}</b> — {u.price_per_night} ₽/ночь")
    await message.answer("\n".join(lines), reply_markup=units_keyboard(units))


@router.callback_query(BookingFSM.choose_unit, F.data.startswith("unit:"))
async def choose_unit(callback: CallbackQuery, state: FSMContext) -> None:
    unit_id = int(callback.data.split(":")[1])
    await state.update_data(unit_id=unit_id)
    await state.set_state(BookingFSM.guest_name)
    await callback.message.answer("Как вас зовут?")
    await callback.answer()


@router.message(BookingFSM.guest_name)
async def got_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Укажите имя (минимум 2 символа).")
        return
    await state.update_data(guest_name=name)
    await state.set_state(BookingFSM.guest_phone)
    await message.answer("Ваш телефон для связи:")


@router.message(BookingFSM.guest_phone)
async def got_phone(message: Message, state: FSMContext, owner_id: int) -> None:
    phone = (message.text or "").strip()
    if len(phone) < 5:
        await message.answer("Укажите телефон покороче не получится — минимум 5 символов.")
        return

    data = await state.get_data()
    check_in = date.fromisoformat(data["check_in"])
    check_out = date.fromisoformat(data["check_out"])
    unit_id = int(data["unit_id"])

    async with SessionLocal() as session:
        booking = await create_booking(
            session,
            owner_id=owner_id,
            unit_id=unit_id,
            guest_name=data["guest_name"],
            guest_phone=phone,
            check_in=check_in,
            check_out=check_out,
            guest_telegram_id=message.from_user.id if message.from_user else None,
        )

    await state.clear()
    if booking is None:
        await message.answer(
            "К сожалению, объект уже занят. Попробуйте другие даты.",
            reply_markup=main_menu(),
        )
        return

    await message.answer(
        f"Заявка #{booking.id} отправлена хозяину.\n"
        f"{check_in.strftime('%d.%m.%Y')} → {check_out.strftime('%d.%m.%Y')}\n"
        "Он свяжется с вами по телефону.",
        reply_markup=main_menu(),
    )
