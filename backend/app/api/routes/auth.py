"""Routes: self-serve signup, password login, emailed one-time code, session lifecycle.

Both entry points converge on the same two-request handshake:

    POST /auth/signup      email + name + password  -> mails a code, sets a pending cookie
    POST /auth/login       email + password         -> mails a code, sets a pending cookie
    POST /auth/verify      the code                 -> clears pending; the session is live

The cookie is issued at step one deliberately: it carries the "which user is halfway
through logging in" state, so no second token type has to be minted, transported, and
separately expired. A pending session authorises nothing — `require_user` rejects it —
and it is destroyed outright after `max_otp_attempts` bad codes, which caps guessing at
a handful of tries per password entry rather than per code.

Signup is open, but only to addresses inside INTERNAL_EMAIL_DOMAINS. That list is the
real access-control boundary here: the mailed code proves you own an inbox, and owning
an inbox is only meaningful because we already decided that inbox belongs to someone
who should see the company's call transcripts.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SESSION_COOKIE, current_session, require_user
from app.config import get_settings
from app.core.db import get_session
from app.core.email import EmailDeliveryError, send_login_code, send_password_reset_code
from app.core.logging import get_logger
from app.core.security import (
    hash_otp_code,
    hash_password,
    hash_session_token,
    needs_rehash,
    new_otp_code,
    new_session_token,
    verify_otp_code,
    verify_password,
)
from app.models.user import User, UserSession
from app.schemas.auth import (
    ForgotPasswordIn,
    ForgotPasswordOut,
    LoginIn,
    LoginOut,
    MeOut,
    OtpVerifyIn,
    PasswordChangeIn,
    ResendOut,
    ResetPasswordIn,
    SignupIn,
)

log = get_logger(__name__)

router = APIRouter(tags=["auth"], prefix="/auth")

# Argon2 hash of a throwaway value, verified against when the email doesn't exist so
# that a missing account and a wrong password take the same time to answer. Without
# it, response latency tells an attacker which addresses are registered.
_DUMMY_HASH = hash_password("meetingmind-timing-equalizer")


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=s.session_ttl_hours * 3600,
        httponly=True,  # unreadable from JS: an XSS bug can't exfiltrate the session
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,
        domain=s.cookie_domain,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(
        SESSION_COOKIE, domain=s.cookie_domain, path="/", samesite=s.cookie_samesite
    )


async def _revoke_other_sessions(db: AsyncSession, user: User, keep_id) -> None:
    """Sign the user out everywhere except the session making this request.

    Called when the password changes: a reset must not leave an attacker's older
    session alive.
    """
    await db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != keep_id)
    )


async def _start_pending_session(
    db: AsyncSession, user: User, *, user_agent: str | None
) -> tuple[UserSession, str]:
    """Create a half-authenticated session. Returns the row and its raw token."""
    s = get_settings()
    token = new_session_token()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        otp_pending=True,
        expires_at=_utcnow() + dt.timedelta(hours=s.session_ttl_hours),
        user_agent=(user_agent or "")[:500] or None,
    )
    db.add(session)
    return session, token


async def _issue_code(db: AsyncSession, session: UserSession, user: User) -> None:
    """Mint a code, stamp it on the session, and mail it.

    The mail is sent BEFORE the caller commits. A failed send therefore rolls the whole
    request back — no user row, no pending session, no code the recipient will never
    see — and the client gets an error it can act on instead of a login screen waiting
    on mail that isn't coming.

    Issuing again replaces any outstanding code, so a resend invalidates the previous
    message rather than leaving two live codes in the inbox.
    """
    s = get_settings()
    code = new_otp_code(s.otp_length)

    session.otp_code_hash = hash_otp_code(code)
    session.otp_expires_at = _utcnow() + dt.timedelta(minutes=s.otp_ttl_minutes)
    session.otp_sent_at = _utcnow()
    session.otp_attempts = 0

    try:
        await send_login_code(user.email, user.name, code, ttl_minutes=s.otp_ttl_minutes)
    except EmailDeliveryError:
        raise HTTPException(502, "We couldn't send your code right now. Please try again.")


def _reject_external_domain(email: str) -> None:
    """Signup is restricted to the company's own domains — see the module docstring."""
    domains = get_settings().internal_email_domains or []
    if domains and email.rsplit("@", 1)[-1] not in domains:
        raise HTTPException(
            403, f"Fennec accounts are limited to {', '.join('@' + d for d in domains)}"
        )


def _login_out(user: User) -> LoginOut:
    return LoginOut(
        email=user.email,
        name=user.name,
        resend_after_seconds=get_settings().otp_resend_seconds,
    )


# --- Signup -------------------------------------------------------------------


@router.post("/signup", response_model=LoginOut)
async def signup(
    payload: SignupIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
):
    """Create an account and mail the first code.

    An address that signed up but never verified can be claimed again, which is what
    makes a typo recoverable — the row exists but has never authenticated anything, so
    overwriting its name and password gives nothing away. A *verified* address is
    refused outright. That does reveal the address is registered, which is a trade we
    accept: signup is already restricted to our own domains, so the only people who can
    learn anything are people who work here.
    """
    email = payload.email.strip().lower()
    _reject_external_domain(email)

    user = (await db.execute(select(User).where(User.email == email))).scalars().first()

    if user is not None and (user.email_verified or not user.is_active):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")

    if user is None:
        user = User(
            email=email, name=payload.name.strip(), password_hash=hash_password(payload.password)
        )
        db.add(user)
    else:
        user.name = payload.name.strip()
        user.password_hash = hash_password(payload.password)
    # The session row needs user.id, which only exists once the INSERT has run.
    await db.flush()

    # An abandoned signup leaves pending sessions behind; none of them should survive
    # a re-claim of the same address.
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))

    session, token = await _start_pending_session(
        db, user, user_agent=request.headers.get("user-agent")
    )
    await _issue_code(db, session, user)
    await db.commit()
    _set_session_cookie(response, token)

    log.info("Signup started for %s", email)
    return _login_out(user)


# --- Login --------------------------------------------------------------------


@router.post("/login", response_model=LoginOut)
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
):
    """Verify the password, then mail a code and issue a pending session cookie."""
    s = get_settings()
    email = payload.email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalars().first()

    if user is not None and user.locked_until and user.locked_until > _utcnow():
        raise HTTPException(429, "Too many failed attempts. Try again later.")

    # Always hash something, so the timing is identical for unknown accounts.
    ok = verify_password(payload.password, user.password_hash if user else _DUMMY_HASH)

    if user is None or not ok or not user.is_active:
        if user is not None and user.is_active:
            user.failed_attempts += 1
            if user.failed_attempts >= s.max_login_attempts:
                user.locked_until = _utcnow() + dt.timedelta(minutes=s.lockout_minutes)
                user.failed_attempts = 0
                log.warning("Account locked after repeated failures: %s", email)
            await db.commit()
        # One message for every failure mode: no account enumeration.
        raise HTTPException(401, "Invalid email or password")

    user.failed_attempts = 0
    user.locked_until = None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    session, token = await _start_pending_session(
        db, user, user_agent=request.headers.get("user-agent")
    )
    await _issue_code(db, session, user)
    await db.commit()
    _set_session_cookie(response, token)

    return _login_out(user)


# --- One-time code ------------------------------------------------------------


@router.post("/verify", response_model=MeOut)
async def verify(
    payload: OtpVerifyIn,
    response: Response,
    found: tuple[UserSession, User] = Depends(current_session),
    db: AsyncSession = Depends(get_session),
):
    """Redeem the mailed code and promote the pending session to a live one.

    The same endpoint finishes a signup and a login. Redeeming a code proves the person
    holding this session can read mail at the account's address, which is exactly the
    claim `email_verified` records — so signup needs no separate confirmation step.
    """
    session, user = found
    s = get_settings()

    if not session.otp_pending:
        raise HTTPException(409, "This session is already fully authenticated")
    if not session.otp_code_hash or not session.otp_expires_at:
        raise HTTPException(409, "No code was requested for this session")

    if session.otp_expires_at <= _utcnow():
        raise HTTPException(400, "That code has expired. Request a new one.")

    if not verify_otp_code(payload.code, session.otp_code_hash):
        session.otp_attempts += 1
        if session.otp_attempts >= s.max_otp_attempts:
            # Destroy the half-authenticated session: guessing now costs a password too.
            await db.delete(session)
            await db.commit()
            _clear_session_cookie(response)
            raise HTTPException(401, "Too many incorrect codes. Please sign in again.")
        await db.commit()
        raise HTTPException(401, "Invalid code")

    # Burn the code before anything else can go wrong: it cannot be replayed.
    session.otp_code_hash = None
    session.otp_expires_at = None
    session.otp_pending = False
    session.otp_attempts = 0
    session.last_seen_at = _utcnow()

    user.email_verified = True
    user.last_login_at = _utcnow()
    await db.commit()

    log.info("Signed in: %s", user.email)
    return _me_out(session, user)


@router.post("/resend", response_model=ResendOut)
async def resend(
    found: tuple[UserSession, User] = Depends(current_session),
    db: AsyncSession = Depends(get_session),
):
    """Mail a fresh code for a pending session, replacing the outstanding one."""
    session, user = found
    s = get_settings()

    if not session.otp_pending:
        raise HTTPException(409, "This session is already fully authenticated")

    if session.otp_sent_at is not None:
        elapsed = (_utcnow() - session.otp_sent_at).total_seconds()
        if elapsed < s.otp_resend_seconds:
            wait = int(s.otp_resend_seconds - elapsed)
            raise HTTPException(429, f"Please wait {wait}s before requesting another code.")

    await _issue_code(db, session, user)
    await db.commit()
    return ResendOut(resend_after_seconds=s.otp_resend_seconds)


# --- Session ------------------------------------------------------------------


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    found: tuple[UserSession, User] = Depends(current_session),
    db: AsyncSession = Depends(get_session),
):
    """Destroy this session server-side, then clear the cookie."""
    session, _ = found
    await db.delete(session)
    await db.commit()
    _clear_session_cookie(response)


def _me_out(session: UserSession, user: User) -> MeOut:
    return MeOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        email_verified=user.email_verified,
        otp_pending=session.otp_pending,
    )


@router.get("/me", response_model=MeOut)
async def me(found: tuple[UserSession, User] = Depends(current_session)):
    """The current user and how far through the login handshake they are.

    Intentionally NOT behind `require_user`: the frontend calls this to decide whether
    to show the code prompt or the app.
    """
    session, user = found
    return _me_out(session, user)


# --- Password -----------------------------------------------------------------


@router.post("/password", status_code=204)
async def change_password(
    payload: PasswordChangeIn,
    found: tuple[UserSession, User] = Depends(current_session),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    """Change the password and sign out every other session."""
    session, _ = found
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(401, "Incorrect password")
    if payload.new_password == payload.current_password:
        raise HTTPException(422, "The new password must differ from the current one")

    user.password_hash = hash_password(payload.new_password)
    await _revoke_other_sessions(db, user, session.id)
    await db.commit()
    log.info("Password changed for %s", user.email)


# --- Forgotten password -------------------------------------------------------
#
# Two anonymous requests: ask for a code, then spend it on a new password. The code is
# stored on the user row (see models/user.py) so it can never be mistaken for a login.
#
# Neither endpoint tries to hide whether an address is registered. `/auth/signup`
# already answers that question by design — it must, to tell you your account exists —
# so contorting these two to be enumeration-proof would protect nothing while making
# the failure modes silent. They return the same body either way as ordinary hygiene,
# and the domain allowlist keeps the whole surface behind our own mail domain.


@router.post("/password/forgot", response_model=ForgotPasswordOut, status_code=202)
async def forgot_password(payload: ForgotPasswordIn, db: AsyncSession = Depends(get_session)):
    """Mail a reset code, if the address belongs to a usable account."""
    s = get_settings()
    email = payload.email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalars().first()

    if user is None or not user.is_active:
        log.info("Reset requested for unknown or disabled address: %s", email)
        return ForgotPasswordOut(resend_after_seconds=s.otp_resend_seconds)

    # Silently decline to re-send inside the cooldown. Answering 429 here would let
    # anyone use this endpoint to flood a colleague's inbox, one request per minute,
    # and would leak that the address is real.
    if user.reset_sent_at is not None:
        elapsed = (_utcnow() - user.reset_sent_at).total_seconds()
        if elapsed < s.otp_resend_seconds:
            return ForgotPasswordOut(resend_after_seconds=s.otp_resend_seconds)

    code = new_otp_code(s.otp_length)
    user.reset_code_hash = hash_otp_code(code)
    user.reset_expires_at = _utcnow() + dt.timedelta(minutes=s.otp_ttl_minutes)
    user.reset_sent_at = _utcnow()
    user.reset_attempts = 0

    # Mailed before the commit, so a failed send leaves no code the user can't receive.
    try:
        await send_password_reset_code(user.email, user.name, code, ttl_minutes=s.otp_ttl_minutes)
    except EmailDeliveryError:
        raise HTTPException(502, "We couldn't send your code right now. Please try again.")

    await db.commit()
    log.info("Password reset code sent to %s", email)
    return ForgotPasswordOut(resend_after_seconds=s.otp_resend_seconds)


@router.post("/password/reset", status_code=204)
async def reset_password(payload: ResetPasswordIn, db: AsyncSession = Depends(get_session)):
    """Spend a reset code on a new password, and sign the account out everywhere."""
    s = get_settings()
    email = payload.email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalars().first()

    if user is None or not user.is_active or not user.reset_code_hash or not user.reset_expires_at:
        # Equalize the cost of the missing-account path with the wrong-code path.
        verify_otp_code(payload.code, _DUMMY_HASH)
        raise HTTPException(400, "That code isn't valid. Request a new one.")

    if user.reset_expires_at <= _utcnow():
        raise HTTPException(400, "That code has expired. Request a new one.")

    if not verify_otp_code(payload.code, user.reset_code_hash):
        user.reset_attempts += 1
        if user.reset_attempts >= s.max_otp_attempts:
            # Discard the code rather than lock the account: otherwise anyone could
            # lock a colleague out by guessing at reset codes they never asked for.
            _clear_reset(user)
            await db.commit()
            raise HTTPException(400, "Too many incorrect codes. Request a new one.")
        await db.commit()
        raise HTTPException(400, "That code isn't valid. Request a new one.")

    user.password_hash = hash_password(payload.new_password)
    _clear_reset(user)
    # Redeeming a mailed code proves the same thing signing in does.
    user.email_verified = True
    # A reset is what you do when you fear the password leaked. Whoever holds a session
    # on the old one — including this browser — has to sign in again with the new one.
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    # The lockout was protecting a password that no longer exists.
    user.failed_attempts = 0
    user.locked_until = None
    await db.commit()

    log.info("Password reset completed for %s", email)


def _clear_reset(user: User) -> None:
    user.reset_code_hash = None
    user.reset_expires_at = None
    user.reset_sent_at = None
    user.reset_attempts = 0
