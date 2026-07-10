"""Per-user Google OAuth: connect Google accounts without Workspace admin.

Two independent connections ("purposes"), each a normal consent screen — no
domain-wide delegation — whose refresh token we keep to mint short-lived access
tokens on demand:

  - "calendar": the meeting organizer's own calendar (attendee emails via events).
  - "bot": the BOT's Google account — the one that actually joins every meeting.
    Because the bot is a participant, its token can read each finished meeting's
    participant list (Meet REST API) and resolve signed-in participants to real
    emails (People API). This is the deterministic internal-vs-client source: it
    only identifies people, never guesses. The bot account must be on the internal
    Workspace domain for colleague emails to resolve.

Flow: authorization_url(purpose) -> Google consent -> callback with `code` ->
exchange_code() stores the refresh token -> access_token(purpose) refreshes as needed.
"""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.models.google_oauth import GoogleOAuthCredential

log = get_logger(__name__)

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"

CALENDAR = "calendar"
BOT = "bot"

# openid+email so we know which account connected, plus purpose-specific scopes.
SCOPES: dict[str, list[str]] = {
    CALENDAR: [
        "openid",
        "email",
        "https://www.googleapis.com/auth/calendar.readonly",
    ],
    BOT: [
        "openid",
        "email",
        # Read conference records (participants) of meetings the bot attended.
        "https://www.googleapis.com/auth/meetings.space.readonly",
        # Resolve participant user IDs to names/emails via the People API.
        # directory.readonly covers same-domain (Workspace) profiles — the ones
        # that matter for internal classification; contacts covers the rest.
        "https://www.googleapis.com/auth/directory.readonly",
        "https://www.googleapis.com/auth/contacts.readonly",
        "https://www.googleapis.com/auth/contacts.other.readonly",
    ],
}


def is_configured() -> bool:
    s = get_settings()
    return bool(s.google_oauth_client_id and s.google_oauth_client_secret)


def authorization_url(state: str, purpose: str = CALENDAR) -> str:
    """The Google consent URL to send the connecting account to."""
    s = get_settings()
    params = {
        "client_id": s.google_oauth_client_id or "",
        "redirect_uri": s.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES.get(purpose, SCOPES[CALENDAR])),
        "access_type": "offline",  # ask for a refresh token
        "prompt": "consent",  # force a refresh token even on re-connect
        "include_granted_scopes": "true",
        "state": state,
    }
    return str(httpx.URL(AUTH_ENDPOINT, params=params))


async def exchange_code(session: AsyncSession, code: str, purpose: str = CALENDAR) -> str:
    """Trade an auth code for tokens, store the refresh token, return the account email."""
    s = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": s.google_oauth_client_id or "",
                "client_secret": s.google_oauth_client_secret or "",
                "redirect_uri": s.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        r.raise_for_status()
        tokens = r.json()
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        scopes = tokens.get("scope")

        # Identify the account so we can display it and upsert by email.
        ui = await client.get(
            USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"}
        )
        ui.raise_for_status()
        email = (ui.json().get("email") or "").strip().lower()

    if not email or not refresh_token:
        # No refresh_token usually means the user previously consented and Google
        # didn't re-issue one; prompt=consent above is meant to avoid this.
        raise RuntimeError("OAuth exchange did not return an email + refresh token")

    # One credential per purpose: a re-connect (any account) replaces the old one.
    existing = (
        await session.execute(
            select(GoogleOAuthCredential).where(GoogleOAuthCredential.purpose == purpose)
        )
    ).scalars().all()
    for row in existing:
        await session.delete(row)
    await session.flush()  # deletes hit the DB before the insert
    session.add(
        GoogleOAuthCredential(
            email=email, refresh_token=refresh_token, scopes=scopes, purpose=purpose
        )
    )
    await session.commit()
    log.info("Connected Google account %s (purpose=%s)", email, purpose)
    return email


async def connected_account(
    session: AsyncSession, purpose: str = CALENDAR
) -> GoogleOAuthCredential | None:
    """The connected account for a purpose (most recent), or None if not connected."""
    return (
        await session.execute(
            select(GoogleOAuthCredential)
            .where(GoogleOAuthCredential.purpose == purpose)
            .order_by(GoogleOAuthCredential.created_at.desc())
        )
    ).scalars().first()


async def access_token(session: AsyncSession, purpose: str = CALENDAR) -> str | None:
    """A fresh access token for a purpose's connected account, or None."""
    cred = await connected_account(session, purpose)
    if cred is None:
        return None
    s = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            TOKEN_ENDPOINT,
            data={
                "client_id": s.google_oauth_client_id or "",
                "client_secret": s.google_oauth_client_secret or "",
                "refresh_token": cred.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        r.raise_for_status()
        return r.json().get("access_token")


async def disconnect(session: AsyncSession, purpose: str = CALENDAR) -> None:
    """Forget the connected account(s) for a purpose."""
    rows = (
        await session.execute(
            select(GoogleOAuthCredential).where(GoogleOAuthCredential.purpose == purpose)
        )
    ).scalars().all()
    for cred in rows:
        await session.delete(cred)
    await session.commit()
