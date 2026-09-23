from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_owner
from app.db import get_db
from app.models import Owner, Unit

router = APIRouter(prefix="/cabinet/units", tags=["units"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def list_units(
    request: Request,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_db),
):
    units = (
        await session.execute(
            select(Unit)
            .where(Unit.owner_id == owner.id)
            .options(selectinload(Unit.photos))
            .order_by(Unit.id)
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request, "cabinet/units_list.html", {"owner": owner, "units": units}
    )


@router.get("/new", response_class=HTMLResponse)
async def new_unit_form(request: Request, owner: Owner = Depends(get_current_owner)):
    return templates.TemplateResponse(
        request, "cabinet/unit_form.html", {"owner": owner, "unit": None, "error": None}
    )


@router.post("/new")
async def create_unit(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    price_per_night: str = Form("0"),
    capacity: int = Form(2),
    address: str = Form(""),
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    try:
        price = Decimal(price_per_night.replace(",", "."))
    except Exception:
        return templates.TemplateResponse(
            request,
            "cabinet/unit_form.html",
            {"owner": owner, "unit": None, "error": "Некорректная цена"},
            status_code=400,
        )
    unit = Unit(
        owner_id=owner.id,
        title=title.strip(),
        description=description.strip(),
        price_per_night=price,
        capacity=capacity,
        address=address.strip() or None,
    )
    session.add(unit)
    await session.commit()
    return RedirectResponse(f"/cabinet/units/{unit.id}", status_code=303)


@router.get("/{unit_id}", response_class=HTMLResponse)
async def unit_detail(
    unit_id: int,
    request: Request,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_db),
):
    unit = await _get_owner_unit(session, owner.id, unit_id)
    if unit is None:
        return RedirectResponse("/cabinet/units", status_code=303)
    return templates.TemplateResponse(
        request, "cabinet/unit_detail.html", {"owner": owner, "unit": unit}
    )


@router.get("/{unit_id}/edit", response_class=HTMLResponse)
async def edit_unit_form(
    unit_id: int,
    request: Request,
    owner: Owner = Depends(get_current_owner),
    session: AsyncSession = Depends(get_db),
):
    unit = await _get_owner_unit(session, owner.id, unit_id)
    if unit is None:
        return RedirectResponse("/cabinet/units", status_code=303)
    return templates.TemplateResponse(
        request, "cabinet/unit_form.html", {"owner": owner, "unit": unit, "error": None}
    )


@router.post("/{unit_id}/edit")
async def update_unit(
    unit_id: int,
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    price_per_night: str = Form("0"),
    capacity: int = Form(2),
    address: str = Form(""),
    is_published: str | None = Form(None),
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    unit = await _get_owner_unit(session, owner.id, unit_id)
    if unit is None:
        return RedirectResponse("/cabinet/units", status_code=303)
    try:
        price = Decimal(price_per_night.replace(",", "."))
    except Exception:
        return templates.TemplateResponse(
            request,
            "cabinet/unit_form.html",
            {"owner": owner, "unit": unit, "error": "Некорректная цена"},
            status_code=400,
        )
    unit.title = title.strip()
    unit.description = description.strip()
    unit.price_per_night = price
    unit.capacity = capacity
    unit.address = address.strip() or None
    unit.is_published = is_published is not None
    await session.commit()
    return RedirectResponse(f"/cabinet/units/{unit.id}", status_code=303)


async def _get_owner_unit(session: AsyncSession, owner_id: int, unit_id: int) -> Unit | None:
    result = await session.execute(
        select(Unit)
        .where(Unit.id == unit_id, Unit.owner_id == owner_id)
        .options(selectinload(Unit.photos), selectinload(Unit.blocked_dates))
    )
    return result.scalar_one_or_none()
