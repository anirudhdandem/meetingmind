"""Routes: LiveKit room-close webhook -> call-end pipeline (spec step 5)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Header, Request
from sqlalchemy import select

from app.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models.call import Call
from app.services import call_processor

router = APIRouter(tags=["webhooks"])
log = get_logger(__name__)


def _receiver():
    # Imported lazily so the app can boot without the livekit package during early dev.
    from livekit import api

    s = get_settings()
    return api.WebhookReceiver(api.TokenVerifier(s.livekit_api_key, s.livekit_api_secret))


async def _process_room(room_name: str) -> None:
    async with SessionLocal() as db:
        call = (
            await db.execute(select(Call).where(Call.livekit_room == room_name))
        ).scalars().first()
        if call is None:
            log.warning("webhook: no call for room %s", room_name)
            return
        await call_processor.process_call(db, call.id)


@router.post("/webhooks/livekit")
async def livekit_webhook(
    request: Request,
    background: BackgroundTasks,
    authorization: str = Header(default=""),
):
    """Receive LiveKit webhooks. On `room_finished`, queue the call-end pipeline."""
    body = await request.body()
    event = _receiver().receive(body.decode("utf-8"), authorization)

    if event.event == "room_finished" and event.room is not None:
        log.info("webhook: room_finished for %s", event.room.name)
        background.add_task(_process_room, event.room.name)

    return {"received": event.event}
