from fastapi import APIRouter, Request, Response
from aiogram.types import Update

from app.services.bot_runtime import process_update

router = APIRouter(tags=["webhooks"])


@router.post("/tg/{secret}")
async def telegram_webhook(secret: str, request: Request) -> Response:
    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": None})
    await process_update(secret, update)
    return Response(status_code=200)
