from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models import Owner


class NotAuthenticated(Exception):
    """Raised when cabinet routes need a logged-in owner."""


async def get_current_owner(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Owner:
    owner_id = request.session.get("owner_id")
    if not owner_id:
        raise NotAuthenticated()
    result = await session.execute(
        select(Owner)
        .where(Owner.id == owner_id)
        .options(selectinload(Owner.subscription))
    )
    owner = result.scalar_one_or_none()
    if owner is None:
        request.session.clear()
        raise NotAuthenticated()
    return owner


async def get_optional_owner(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Owner | None:
    owner_id = request.session.get("owner_id")
    if not owner_id:
        return None
    result = await session.execute(
        select(Owner)
        .where(Owner.id == owner_id)
        .options(selectinload(Owner.subscription))
    )
    return result.scalar_one_or_none()
