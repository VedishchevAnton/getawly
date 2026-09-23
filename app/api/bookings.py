from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_owner
from app.db import get_db
from app.models import Booking, BookingStatus, Owner
from app.services.booking import occupied_days, set_blocked_dates

router = APIRouter(prefix="/cabinet", tags=["bookings"])
templates = Jinja2Templates(directory="templates")


@router.get("/bookings", response_class=HTMLResponse)
async def bookings_list(
    request: Request,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_db),
):
    bookings = (
        await session.execute(
            select(Booking)
            .where(Booking.owner_id == owner.id)
            .options(selectinload(Booking.unit))
            .order_by(Booking.created_at.desc())
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request, "cabinet/bookings.html", {"owner": owner, "bookings": bookings}
    )


@router.post("/bookings/{booking_id}/status")
async def update_booking_status(
    booking_id: int,
    status: str = Form(...),
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    result = await session.execute(
        select(Booking).where(Booking.id == booking_id, Booking.owner_id == owner.id)
    )
    booking = result.scalar_one_or_none()
    if booking and status in {s.value for s in BookingStatus}:
        booking.status = BookingStatus(status)
        await session.commit()
    return RedirectResponse("/cabinet/bookings", status_code=303)


@router.get("/units/{unit_id}/calendar", response_class=HTMLResponse)
async def unit_calendar(
    unit_id: int,
    request: Request,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_db),
):
    from app.api.units import _get_owner_unit

    unit = await _get_owner_unit(session, owner.id, unit_id)
    if unit is None:
        return RedirectResponse("/cabinet/units", status_code=303)

    today = date.today()
    from datetime import timedelta

    end = today + timedelta(days=60)
    busy = await occupied_days(session, unit.id, today, end)
    days = []
    d = today
    while d < end:
        days.append({"day": d, "busy": d in busy})
        d += timedelta(days=1)

    return templates.TemplateResponse(
        request,
        "cabinet/calendar.html",
        {"owner": owner, "unit": unit, "days": days},
    )


@router.post("/units/{unit_id}/calendar/block")
async def block_day(
    unit_id: int,
    day: str = Form(...),
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    from app.api.units import _get_owner_unit

    unit = await _get_owner_unit(session, owner.id, unit_id)
    if unit is None:
        return RedirectResponse("/cabinet/units", status_code=303)
    await set_blocked_dates(session, unit.id, [date.fromisoformat(day)], note="manual")
    return RedirectResponse(f"/cabinet/units/{unit_id}/calendar", status_code=303)
