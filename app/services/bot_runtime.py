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
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import Owner
from app.services.auth import subscription_is_usable

logger = logging.getLogger(__name__)


def owner_bot_is_active(owner: Owner) -> bool:
    """A bot answers guests only while the owner is active and paid up."""
    return bool(owner.is_active) and subscription_is_usable(owner.subscription)


@dataclass
class OwnerBot:
    owner_id: int
    bot: Bot
    dp: Dispatcher


_cache: dict[str, OwnerBot] = {}


async def get_owner_by_secret(session: AsyncSession, secret: str) -> Owner | None:
    result = await session.execute(
        select(Owner)
        .where(Owner.webhook_secret == secret)
        .options(selectinload(Owner.subscription))
    )
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


async def notify_unavailable(bot: Bot, chat_id: int | None) -> None:
    """Tell the guest the bot is off, and never let that failure escape.

    A revoked token or a guest who blocked the bot would otherwise raise out
    of the webhook handler; Telegram reads a 500 as "retry" and keeps redelivering.
    """
    if chat_id is None:
        return
    try:
        await bot.send_message(chat_id, "Бот временно недоступен. Попробуйте позже.")
    except Exception:
        logger.exception("Could not tell chat %s that the bot is unavailable", chat_id)


def _chat_id_from_update(update: Update) -> int | None:
    if update.message is not None:
        return update.message.chat.id
    if update.callback_query is not None and update.callback_query.message is not None:
        return update.callback_query.message.chat.id
    return None


async def process_update(secret: str, update: Update) -> None:
    """The single choke point every guest message passes through."""
    async with SessionLocal() as session:
        owner = await get_owner_by_secret(session, secret)
        if owner is None:
            logger.warning("Unknown webhook secret")
            return
        allowed = owner_bot_is_active(owner)
        entry = await get_or_create_owner_bot(owner)

    if entry is None:
        return
    if not allowed:
        await notify_unavailable(entry.bot, _chat_id_from_update(update))
        return
    await entry.dp.feed_update(entry.bot, update)
