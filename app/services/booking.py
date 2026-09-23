from datetime import date, timedelta

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BlockedDate, Booking, BookingStatus, Unit


def daterange(start: date, end: date):
    """Half-open [start, end) nights."""
    cur = start
    while cur < end:
        yield cur
        cur += timedelta(days=1)


async def unit_is_available(
    session: AsyncSession,
    unit_id: int,
    check_in: date,
    check_out: date,
    *,
    exclude_booking_id: int | None = None,
) -> bool:
    if check_out <= check_in:
        return False

    blocked = await session.execute(
        select(BlockedDate.id).where(
            BlockedDate.unit_id == unit_id,
            BlockedDate.day >= check_in,
            BlockedDate.day < check_out,
        ).limit(1)
    )
    if blocked.scalar_one_or_none() is not None:
        return False

    q = select(Booking.id).where(
        Booking.unit_id == unit_id,
        Booking.status.in_([BookingStatus.NEW, BookingStatus.CONFIRMED]),
        Booking.check_in < check_out,
        Booking.check_out > check_in,
    )
    if exclude_booking_id is not None:
        q = q.where(Booking.id != exclude_booking_id)
    conflict = await session.execute(q.limit(1))
    return conflict.scalar_one_or_none() is None


async def list_available_units(
    session: AsyncSession,
    owner_id: int,
    check_in: date,
    check_out: date,
) -> list[Unit]:
    result = await session.execute(
        select(Unit)
        .where(Unit.owner_id == owner_id, Unit.is_published.is_(True))
        .options(selectinload(Unit.photos))
        .order_by(Unit.id)
    )
    units = list(result.scalars().all())
    available: list[Unit] = []
    for unit in units:
        if await unit_is_available(session, unit.id, check_in, check_out):
            available.append(unit)
    return available


async def create_booking(
    session: AsyncSession,
    *,
    owner_id: int,
    unit_id: int,
    guest_name: str,
    guest_phone: str,
    check_in: date,
    check_out: date,
    guest_telegram_id: int | None = None,
    comment: str | None = None,
) -> Booking | None:
    ok = await unit_is_available(session, unit_id, check_in, check_out)
    if not ok:
        return None
    booking = Booking(
        owner_id=owner_id,
        unit_id=unit_id,
        guest_name=guest_name.strip(),
        guest_phone=guest_phone.strip(),
        guest_telegram_id=guest_telegram_id,
        check_in=check_in,
        check_out=check_out,
        comment=comment,
        status=BookingStatus.NEW,
    )
    session.add(booking)
    await session.commit()
    await session.refresh(booking)
    return booking


async def set_blocked_dates(
    session: AsyncSession,
    unit_id: int,
    days: list[date],
    *,
    note: str | None = None,
) -> None:
    for day in days:
        exists = await session.execute(
            select(BlockedDate).where(BlockedDate.unit_id == unit_id, BlockedDate.day == day)
        )
        if exists.scalar_one_or_none() is None:
            session.add(BlockedDate(unit_id=unit_id, day=day, note=note))
    await session.commit()


async def clear_blocked_dates(session: AsyncSession, unit_id: int, days: list[date]) -> None:
    await session.execute(
        delete(BlockedDate).where(and_(BlockedDate.unit_id == unit_id, BlockedDate.day.in_(days)))
    )
    await session.commit()


async def occupied_days(session: AsyncSession, unit_id: int, start: date, end: date) -> set[date]:
    blocked = await session.execute(
        select(BlockedDate.day).where(
            BlockedDate.unit_id == unit_id,
            BlockedDate.day >= start,
            BlockedDate.day < end,
        )
    )
    days = set(blocked.scalars().all())

    bookings = await session.execute(
        select(Booking).where(
            Booking.unit_id == unit_id,
            Booking.status.in_([BookingStatus.NEW, BookingStatus.CONFIRMED]),
            Booking.check_in < end,
            Booking.check_out > start,
        )
    )
    for b in bookings.scalars():
        for d in daterange(max(b.check_in, start), min(b.check_out, end)):
            days.add(d)
    return days
