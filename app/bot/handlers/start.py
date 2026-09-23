from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.states import BookingFSM
from app.bot.keyboards import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я помогу подобрать жильё и оставить заявку хозяину.\n\n"
        "Нажмите «Найти жильё», чтобы выбрать даты.",
        reply_markup=main_menu(),
    )


@router.message(F.text == "Найти жильё")
async def find_housing(message: Message, state: FSMContext) -> None:
    await state.set_state(BookingFSM.check_in)
    await message.answer(
        "Введите дату заезда в формате ДД.ММ.ГГГГ\nНапример: 01.10.2026"
    )
