from fastapi import APIRouter

from app.api import admin, auth, bookings, cabinet, payments, units, webhooks

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(cabinet.router)
api_router.include_router(payments.router)
api_router.include_router(units.router)
api_router.include_router(bookings.router)
api_router.include_router(webhooks.router)
