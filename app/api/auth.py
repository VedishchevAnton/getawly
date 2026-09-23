from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_optional_owner
from app.db import get_db
from app.models import Owner
from app.services.auth import authenticate_owner, register_owner

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, owner: Owner | None = Depends(get_optional_owner)):
    if owner:
        return RedirectResponse("/cabinet", status_code=303)
    return templates.TemplateResponse(request, "landing.html", {"owner": owner})


@router.get("/register", response_class=HTMLResponse)
async def register_form(request: Request, owner: Owner | None = Depends(get_optional_owner)):
    if owner:
        return RedirectResponse("/cabinet", status_code=303)
    return templates.TemplateResponse(request, "auth/register.html", {"error": None})


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    phone: str = Form(""),
    session: AsyncSession = Depends(get_db),
):
    try:
        owner = await register_owner(
            session,
            email=email,
            password=password,
            name=name,
            phone=phone or None,
        )
    except IntegrityError:
        await session.rollback()
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "Не удалось зарегистрироваться. Возможно, email уже занят."},
            status_code=400,
        )
    request.session["owner_id"] = owner.id
    return RedirectResponse("/cabinet", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, owner: Owner | None = Depends(get_optional_owner)):
    if owner:
        return RedirectResponse("/cabinet", status_code=303)
    return templates.TemplateResponse(request, "auth/login.html", {"error": None})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_db),
):
    owner = await authenticate_owner(session, email, password)
    if owner is None:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Неверный email или пароль"},
            status_code=400,
        )
    request.session["owner_id"] = owner.id
    return RedirectResponse("/cabinet", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)
