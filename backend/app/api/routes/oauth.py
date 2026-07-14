"""Routes: per-user Google OAuth connections.

Two purposes share one flow: "calendar" (the signed-in user's own calendar — one
connection per app user, powering auto-join + attendee emails) and "bot" (the
bot's own Google account, app-wide, for the Meet participant list + People API
email resolution — the deterministic internal-vs-client source).

The whole router sits behind require_user (see main.py), including the Google
callback: cookie_samesite=lax sends the session cookie on that top-level
redirect, which is how a calendar connection gets tied to the right app user.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_user
from app.config import get_settings
from app.core.db import get_session
from app.core.logging import get_logger
from app.google import oauth
from app.models.user import User

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
    purpose: str = oauth.CALENDAR,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
) -> dict:
    """Whether an account is connected for this purpose — the caller's own, for calendar."""
    cred = await oauth.connected_account(db, _check_purpose(purpose), user.id)
    return {
        "configured": oauth.is_configured(),
        "connected": cred is not None,
        "email": cred.email if cred else None,
        # Calendar auto-join needs the bot connection to carry calendar.readonly.
        # A bot account connected before that scope existed reports False here —
        # the Settings page uses it to ask for a one-time reconnect.
        "has_calendar_scope": bool(
            cred and cred.scopes and "auth/calendar.readonly" in cred.scopes
        ),
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
    user: User = Depends(require_user),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Google redirects here with an auth code; store the refresh token.

    A calendar connection is stored against the signed-in user (their session
    cookie rides along on this top-level redirect); the bot stays app-wide.
    """
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
        email = await oauth.exchange_code(db, code, purpose, user.id)
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
    purpose: str = oauth.CALENDAR,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    """Disconnect a slot's account (the caller's own, for calendar)."""
    await oauth.disconnect(db, _check_purpose(purpose), user.id)
