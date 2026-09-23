from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_owner
from app.db import get_db
from app.models import Owner, Unit, UnitPhoto
from app.services import photos
from app.services.photos import MAX_BYTES, save_photo, validate_photo

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
        request, "cabinet/unit_detail.html", {"owner": owner, "unit": unit, "error": None}
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


@router.post("/{unit_id}/photos")
async def upload_photo(
    unit_id: int,
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    unit = await _get_owner_unit(session, owner.id, unit_id)
    if unit is None:
        return RedirectResponse("/cabinet/units", status_code=303)

    # One byte past the limit is enough to tell "at the limit" from "over it"
    # without pulling an arbitrarily large upload into memory.
    data = await file.read(MAX_BYTES + 1)
    # Counted in the database rather than off unit.photos: the limit is a
    # correctness check and must not read a collection loaded earlier.
    existing = (
        await session.execute(
            select(func.count()).select_from(UnitPhoto).where(UnitPhoto.unit_id == unit.id)
        )
    ).scalar_one()

    extension, error = validate_photo(file.content_type, len(data), existing)
    if error is not None:
        return templates.TemplateResponse(
            request,
            "cabinet/unit_detail.html",
            {"owner": owner, "unit": unit, "error": error},
            status_code=400,
        )

    path = await save_photo(unit.id, data, extension)
    session.add(UnitPhoto(unit_id=unit.id, path=path, sort_order=existing))
    await session.commit()
    return RedirectResponse(f"/cabinet/units/{unit.id}", status_code=303)


@router.post("/{unit_id}/photos/{photo_id}/delete")
async def delete_photo(
    unit_id: int,
    photo_id: int,
    session: AsyncSession = Depends(get_db),
    owner: Owner = Depends(get_current_owner),
):
    unit = await _get_owner_unit(session, owner.id, unit_id)
    if unit is None:
        return RedirectResponse("/cabinet/units", status_code=303)

    # Fetched by (id, unit_id) instead of scanning unit.photos so ownership
    # is enforced by the query rather than by whatever the session cached.
    photo = (
        await session.execute(
            select(UnitPhoto).where(UnitPhoto.id == photo_id, UnitPhoto.unit_id == unit.id)
        )
    ).scalar_one_or_none()
    if photo is not None:
        (photos.UPLOAD_ROOT / photo.path).unlink(missing_ok=True)
        await session.delete(photo)
        await session.commit()
    return RedirectResponse(f"/cabinet/units/{unit.id}", status_code=303)


async def _get_owner_unit(session: AsyncSession, owner_id: int, unit_id: int) -> Unit | None:
    result = await session.execute(
        select(Unit)
        .where(Unit.id == unit_id, Unit.owner_id == owner_id)
        .options(selectinload(Unit.photos), selectinload(Unit.blocked_dates))
    )
    return result.scalar_one_or_none()
