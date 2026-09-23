import logging

from aiogram.types import Update
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Payment
from app.services.bot_runtime import process_update
from app.services.payments import YooKassaProvider, apply_successful_payment

router = APIRouter(tags=["webhooks"])
logger = logging.getLogger(__name__)


async def fetch_yookassa_status(external_id: str) -> str:
    """Indirection kept module-level so tests can replace it."""
    return await YooKassaProvider().fetch_status(external_id)


@router.post("/tg/{secret}")
async def telegram_webhook(secret: str, request: Request) -> Response:
    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": None})
    await process_update(secret, update)
    return Response(status_code=200)


@router.post("/webhooks/yookassa")
async def yookassa_webhook(
    request: Request, session: AsyncSession = Depends(get_db)
) -> Response:
    """Always answers 200: YooKassa retries anything else until it succeeds.

    The notification body is unsigned, so it is treated as a hint only — the
    authoritative status is fetched back from the API.
    """
    body = await request.json()
    external_id = (body.get("object") or {}).get("id")
    if not external_id:
        return Response(status_code=200)

    payment = (
        await session.execute(select(Payment).where(Payment.external_id == external_id))
    ).scalar_one_or_none()
    if payment is None:
        logger.warning("YooKassa notification for unknown payment %s", external_id)
        return Response(status_code=200)

    try:
        status = await fetch_yookassa_status(external_id)
    except Exception:
        logger.exception("Could not verify YooKassa payment %s", external_id)
        return Response(status_code=200)

    if status == "succeeded":
        await apply_successful_payment(session, payment)
    return Response(status_code=200)
