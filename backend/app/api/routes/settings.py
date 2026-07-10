from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_session
from app.models.notification import NotificationSettings
from app.schemas.settings import NotificationSettingsIn, NotificationSettingsOut

router = APIRouter(tags=["settings"])


async def _get_or_create_notifications(db: AsyncSession) -> NotificationSettings:
    """The notification settings are a singleton: reuse the first row, or seed one."""
    row = (await db.execute(select(NotificationSettings))).scalars().first()
    if row is None:
        row = NotificationSettings()
        db.add(row)
        await db.flush()
    return row


@router.get("/settings/status")
async def settings_status(db: AsyncSession = Depends(get_session)) -> dict:
    s = get_settings()
    notif = (await db.execute(select(NotificationSettings))).scalars().first()
    return {
        "bot": {
            "display_name": s.bot_display_name,
            "account_email": s.bot_google_account_email,
            "password_set": bool(s.bot_google_account_password),
            "headless": s.bot_headless,
            "profile_dir": s.bot_user_data_dir,
            # A persisted Chromium profile + an account email is what keeps the
            # bot signed in across runs; treat both present as "ready".
            "configured": bool(s.bot_google_account_email),
        },
        "transcription": {
            "provider": "Deepgram",
            "model": s.deepgram_model,
            "language": s.deepgram_language,
            "configured": bool(s.deepgram_api_key),
        },
        "llm": {
            "provider": "Gemini",
            "model": s.gemini_llm_model,
            "embed_model": s.gemini_embed_model,
            "configured": bool(s.gemini_api_key),
        },
        "livekit": {
            "url": s.livekit_url,
            "configured": bool(s.livekit_api_key and s.livekit_api_secret),
        },
        "meet_api": {
            "impersonate_subject": s.google_impersonate_subject,
            "configured": bool(s.google_service_account_file and s.google_impersonate_subject),
        },
        "notifications": {
            "slack_configured": bool(notif and notif.slack_webhook_url),
            "email_configured": bool(notif and notif.notification_email),
        },
    }


@router.get("/settings/notifications", response_model=NotificationSettingsOut)
async def get_notifications(db: AsyncSession = Depends(get_session)):
    """Current notification destinations, so the Settings form can prefill them."""
    return await _get_or_create_notifications(db)


@router.put("/settings/notifications", response_model=NotificationSettingsOut)
async def save_notifications(
    payload: NotificationSettingsIn, db: AsyncSession = Depends(get_session)
):
    """Save the Slack webhook / email. Blank values clear the destination."""
    row = await _get_or_create_notifications(db)
    # Treat empty/whitespace-only strings as "unset" so the badges read correctly.
    row.slack_webhook_url = (payload.slack_webhook_url or "").strip() or None
    row.notification_email = (payload.notification_email or "").strip() or None
    await db.commit()
    await db.refresh(row)
    return row
