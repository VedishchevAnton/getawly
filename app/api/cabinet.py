from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_owner
from app.config import settings
from app.db import get_db
from app.models import Booking, Owner, Unit
from app.services.auth import subscription_is_usable
from app.services.bot_runtime import drop_owner_bot, get_or_create_owner_bot, set_owner_webhook

router = APIRouter(prefix="/cabinet", tags=["cabinet"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_db),
):
    units = (
        await session.execute(select(Unit).where(Unit.owner_id == owner.id).order_by(Unit.id))
    ).scalars().all()
    bookings = (
        await session.execute(
            select(Booking)
            .where(Booking.owner_id == owner.id)
            .options(selectinload(Booking.unit))
            .order_by(Booking.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    sub_ok = subscription_is_usable(owner.subscription)
    return templates.TemplateResponse(
        request,
        "cabinet/dashboard.html",
        {
            "owner": owner,
            "units": units,
            "bookings": bookings,
            "sub_ok": sub_ok,
            "trial_days": settings.trial_days,
        },
    )


@router.get("/bot", response_class=HTMLResponse)
async def bot_settings(request: Request, owner: Owner = Depends(get_current_owner)):
    return templates.TemplateResponse(
        request,
        "cabinet/bot.html",
        {"owner": owner, "error": None, "ok": None, "webhook_url": None},
    )


@router.post("/bot")
async def save_bot(
    request: Request,
    bot_token: str = Form(...),
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    token = bot_token.strip()
    if ":" not in token or len(token) < 20:
        return templates.TemplateResponse(
            request,
            "cabinet/bot.html",
            {"owner": owner, "error": "Похоже, токен неверный", "ok": None, "webhook_url": None},
            status_code=400,
        )

    old_secret = owner.webhook_secret
    owner.bot_token = token
    await session.commit()
    await session.refresh(owner)

    await drop_owner_bot(old_secret)
    try:
        webhook_url = await set_owner_webhook(owner)
        entry = await get_or_create_owner_bot(owner)
        if entry:
            me = await entry.bot.get_me()
            owner.bot_username = me.username
            await session.commit()
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "cabinet/bot.html",
            {
                "owner": owner,
                "error": f"Токен сохранён, но webhook не удалось поставить: {exc}",
                "ok": None,
                "webhook_url": None,
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "cabinet/bot.html",
        {
            "owner": owner,
            "error": None,
            "ok": "Бот подключён, webhook обновлён",
            "webhook_url": webhook_url,
        },
    )


@router.get("/subscription", response_class=HTMLResponse)
async def subscription_page(request: Request, owner: Owner = Depends(get_current_owner)):
    return templates.TemplateResponse(
        request,
        "cabinet/subscription.html",
        {
            "owner": owner,
            "sub_ok": subscription_is_usable(owner.subscription),
            "trial_days": settings.trial_days,
            "price": settings.subscription_price_rub,
            "period_days": settings.subscription_period_days,
        },
    )
