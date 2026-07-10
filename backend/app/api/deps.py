"""Request-scoped authentication dependencies.

`require_user` is the ONE place that decides whether a request is authenticated. Every
protected router hangs off it, so there is a single function to audit rather than a
check repeated per route (and eventually forgotten on one).

A request is authenticated only when all of these hold:
  1. the session cookie names a session row that exists and has not expired;
  2. that session is not `otp_pending` — a correct password alone authenticates nothing;
  3. the owning user is active.

There is no separate "email verified" check here, and that is deliberate rather than an
omission: the only thing that clears `otp_pending` is redeeming a code sent to the
user's address, and redeeming it marks the address verified. A non-pending session
therefore cannot belong to an unverified user.
"""

from __future__ import annotations

import datetime as dt

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import hash_session_token
from app.models.user import User, UserSession

SESSION_COOKIE = "mm_session"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(401, detail)


async def load_session(
    db: AsyncSession, token: str | None
) -> tuple[UserSession, User] | None:
    """The live session + its user for a raw cookie token, or None.

    Expired rows are deleted on sight rather than merely ignored, which keeps the
    table from growing without a separate reaper job.
    """
    if not token:
        return None
    row = (
        await db.execute(
            select(UserSession)
            .where(UserSession.token_hash == hash_session_token(token))
            .options(selectinload(UserSession.user))
        )
    ).scalars().first()
    if row is None:
        return None
    if row.expires_at <= _utcnow():
        await db.delete(row)
        await db.commit()
        return None
    if row.user is None or not row.user.is_active:
        return None
    return row, row.user


async def current_session(
    mm_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_session),
) -> tuple[UserSession, User]:
    """A session row that exists, is unexpired, and belongs to an active user.

    Says nothing about the second factor — only `require_user` and the OTP endpoints
    interpret `otp_pending`. Do not depend on this directly from a business route.
    """
    found = await load_session(db, mm_session)
    if found is None:
        raise _unauthorized()
    return found


async def require_user(
    found: tuple[UserSession, User] = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> User:
    """The authenticated user, both factors complete. The guard for every protected route."""
    session, user = found

    if session.otp_pending:
        raise _unauthorized("Verification code required")

    # Cheap liveness stamp; skip the write unless it's meaningfully stale so a busy
    # dashboard doesn't issue an UPDATE per request.
    now = _utcnow()
    if session.last_seen_at is None or (now - session.last_seen_at) > dt.timedelta(minutes=5):
        session.last_seen_at = now
        await db.commit()

    return user
