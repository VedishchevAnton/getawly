from aiogram import Router

from app.bot.handlers import booking, start


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(booking.router)
    return root
