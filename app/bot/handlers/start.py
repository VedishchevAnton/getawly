from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards import main_menu
from app.bot.states import BookingFSM
from app.db import SessionLocal
from app.services.auth import link_owner_chat

router = Router()


async def _greet_guest(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я помогу подобрать жильё и оставить заявку хозяину.\n\n"
        "Нажмите «Найти жильё», чтобы выбрать даты.",
        reply_markup=main_menu(),
    )


@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(
    message: Message, command: CommandObject, state: FSMContext, owner_id: int
) -> None:
    """Registered before the plain /start so the payload gets a chance to match."""
    async with SessionLocal() as session:
        linked = await link_owner_chat(session, owner_id, command.args, message.chat.id)

    if linked:
        await state.clear()
        await message.answer("Готово! Сюда будут приходить заявки от гостей.")
        return
    await _greet_guest(message, state)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await _greet_guest(message, state)


@router.message(F.text == "Найти жильё")
async def find_housing(message: Message, state: FSMContext) -> None:
    await state.set_state(BookingFSM.check_in)
    await message.answer("Введите дату заезда в формате ДД.ММ.ГГГГ\nНапример: 01.10.2026")
