from aiogram.fsm.state import State, StatesGroup


class BookingFSM(StatesGroup):
    check_in = State()
    check_out = State()
    choose_unit = State()
    guest_name = State()
    guest_phone = State()
