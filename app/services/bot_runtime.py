"""Per-owner Telegram bot runtime (aiogram 3 webhook).

Each owner stores their own bot token. Webhooks hit:
  POST /tg/{webhook_secret}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionLocal
from app.models import Owner

logger = logging.getLogger(__name__)


@dataclass
class OwnerBot:
    owner_id: int
    bot: Bot
    dp: Dispatcher


_cache: dict[str, OwnerBot] = {}


async def get_owner_by_secret(session: AsyncSession, secret: str) -> Owner | None:
    result = await session.execute(select(Owner).where(Owner.webhook_secret == secret))
    return result.scalar_one_or_none()


def build_dispatcher(owner_id: int) -> Dispatcher:
    from app.bot.handlers import setup_routers
    from app.bot.storage import fsm_storage

    dp = Dispatcher(storage=fsm_storage)
    dp["owner_id"] = owner_id
    dp.include_router(setup_routers())
    return dp


async def get_or_create_owner_bot(owner: Owner) -> OwnerBot | None:
    if not owner.bot_token or not owner.webhook_secret:
        return None
    secret = owner.webhook_secret
    cached = _cache.get(secret)
    if cached and cached.owner_id == owner.id:
        return cached

    bot = Bot(
        token=owner.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(owner.id)
    entry = OwnerBot(owner_id=owner.id, bot=bot, dp=dp)
    _cache[secret] = entry
    return entry


async def drop_owner_bot(secret: str | None) -> None:
    if not secret:
        return
    entry = _cache.pop(secret, None)
    if entry:
        await entry.bot.session.close()


async def set_owner_webhook(owner: Owner) -> str | None:
    """Register Telegram webhook for this owner's bot. Returns webhook URL."""
    if not owner.bot_token or not owner.webhook_secret:
        return None
    entry = await get_or_create_owner_bot(owner)
    if entry is None:
        return None
    url = f"{settings.base_url.rstrip('/')}/tg/{owner.webhook_secret}"
    await entry.bot.set_webhook(url=url, drop_pending_updates=True)
    return url


async def process_update(secret: str, update: Update) -> None:
    async with SessionLocal() as session:
        owner = await get_owner_by_secret(session, secret)
        if owner is None or not owner.is_active:
            logger.warning("Unknown or inactive webhook secret")
            return
        entry = await get_or_create_owner_bot(owner)
        if entry is None:
            return
    await entry.dp.feed_update(entry.bot, update)
