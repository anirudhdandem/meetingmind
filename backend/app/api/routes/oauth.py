"""Routes: per-user Google OAuth connections.

Two purposes share one flow: "calendar" (organizer's calendar, for attendee emails
from events) and "bot" (the bot's own Google account, for the Meet participant list
+ People API email resolution — the deterministic internal-vs-client source).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_session
from app.core.logging import get_logger
from app.google import oauth

log = get_logger(__name__)

router = APIRouter(tags=["oauth"])

_STATE_COOKIE = "g_oauth_state"
_PURPOSES = (oauth.CALENDAR, oauth.BOT)


def _check_purpose(purpose: str) -> str:
    if purpose not in _PURPOSES:
        raise HTTPException(422, f"purpose must be one of {_PURPOSES}")
    return purpose


@router.get("/oauth/google/status")
async def google_status(
    purpose: str = oauth.CALENDAR, db: AsyncSession = Depends(get_session)
) -> dict:
    """Whether an account is connected for this purpose, and which one."""
    cred = await oauth.connected_account(db, _check_purpose(purpose))
    return {
        "configured": oauth.is_configured(),
        "connected": cred is not None,
        "email": cred.email if cred else None,
    }


@router.get("/oauth/google/start")
async def google_start(purpose: str = oauth.CALENDAR):
    """Kick off the consent flow: redirect the browser to Google."""
    _check_purpose(purpose)
    if not oauth.is_configured():
        raise HTTPException(400, "Google OAuth is not configured on the server")
    state = secrets.token_urlsafe(24)
    resp = RedirectResponse(oauth.authorization_url(state, purpose))
    # Short-lived, HTTP-only cookie: CSRF state + which purpose is being connected
    # (the callback URL is registered with Google and can't carry a query param).
    resp.set_cookie(
        _STATE_COOKIE, f"{state}:{purpose}", max_age=600, httponly=True, samesite="lax"
    )
    return resp


@router.get("/oauth/google/callback")
async def google_callback(
    request: Request,
    db: AsyncSession = Depends(get_session),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Google redirects here with an auth code; store the refresh token."""
    settings = get_settings()
    dest = f"{settings.app_base_url.rstrip('/')}/settings"

    expected, _, purpose = (request.cookies.get(_STATE_COOKIE) or "").partition(":")
    if purpose not in _PURPOSES:
        purpose = oauth.CALENDAR
    if error:
        return RedirectResponse(f"{dest}?google=error&purpose={purpose}")
    if not code or not state or state != expected:
        return RedirectResponse(f"{dest}?google=error&purpose={purpose}")

    try:
        email = await oauth.exchange_code(db, code, purpose)
    except Exception:
        log.exception("Google OAuth code exchange failed (purpose=%s)", purpose)
        return RedirectResponse(f"{dest}?google=error&purpose={purpose}")

    # Guard against the classic slip: connecting the wrong Google account as "the
    # bot". It must be the account that actually joins meetings, or the Meet API
    # will find no conference records for it. Stored anyway; surfaced as a warning.
    if purpose == oauth.BOT:
        expected_bot = (settings.bot_google_account_email or "").strip().lower()
        if expected_bot and email != expected_bot:
            log.warning(
                "Bot OAuth connected as %s but BOT_GOOGLE_ACCOUNT_EMAIL is %s — "
                "participant lookup will fail until these match",
                email, expected_bot,
            )
            resp = RedirectResponse(f"{dest}?google=bot_mismatch&purpose=bot")
            resp.delete_cookie(_STATE_COOKIE)
            return resp

    resp = RedirectResponse(f"{dest}?google=connected&purpose={purpose}")
    resp.delete_cookie(_STATE_COOKIE)
    return resp


@router.delete("/oauth/google", status_code=204)
async def google_disconnect(
    purpose: str = oauth.CALENDAR, db: AsyncSession = Depends(get_session)
):
    """Disconnect a purpose's account (forget its stored token)."""
    await oauth.disconnect(db, _check_purpose(purpose))
