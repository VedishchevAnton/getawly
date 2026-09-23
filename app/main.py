"""Getawly — SaaS for short-term rental hosts with per-owner Telegram bots."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.deps import NotAuthenticated
from app.api.router import api_router
from app.config import settings
from app.db import engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.app_env == "production",
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(_request: Request, _exc: NotAuthenticated):
    return RedirectResponse("/login", status_code=303)
