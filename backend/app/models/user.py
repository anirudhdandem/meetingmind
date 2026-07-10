"""ORM models: application users and their sessions.

MeetingMind holds every call transcript and MOM the company produces, so the API is
closed by default: one account per employee, password plus a one-time code mailed to
that employee's address.

Sessions are OPAQUE tokens stored server-side rather than self-contained JWTs. The
cost is a lookup per request; the benefit is that logout, "sign out everywhere", and
automatic revocation on password change are real rather than best-effort. Only the
SHA-256 of a session token is stored — a database dump does not yield live sessions.

The pending session IS the login handshake's state. A correct password creates a row
with `otp_pending` set and the mailed code's hash beside it; a correct code clears the
flag. Keeping the half-finished login on the session row means the request guard has
exactly one thing to check, instead of a second short-lived token type to mint,
transport, and expire correctly. It also means the code dies with the session: a few
wrong guesses destroy the row, and the next attempt costs a password again.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class User(Base, UUIDPk, Timestamped):
    __tablename__ = "users"

    # Stored lowercased; the unique index is the real guard against duplicates.
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Argon2id. Never a plaintext or reversible form.
    password_hash: Mapped[str] = mapped_column(String, nullable=False)

    # Set the first time a mailed code is redeemed, which proves whoever signed up can
    # read mail at this address. Until then the account can be re-claimed by a fresh
    # signup, so a mistyped address doesn't squat a real one forever.
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    # Soft disable — preserves the audit trail a delete would erase.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    # Password brute-force throttle. Reset on any successful password check.
    failed_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    locked_until: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    last_login_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Outstanding password-reset code, Argon2-hashed like every other one-time code.
    #
    # This lives on the user and NOT on a pending session, which is the whole point:
    # a reset is requested by someone who is not logged in, and if the code were held
    # by a session then `/auth/verify` would happily promote that session to a live
    # login. "I forgot my password" would become "let me in without one". Keeping the
    # code here means the only thing it can buy is a new password.
    #
    # It also means the code is redeemable from any browser — request it on a phone,
    # finish on a laptop — because nothing about it is tied to a cookie.
    reset_code_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    reset_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the outstanding reset code was mailed. Backs the resend cooldown.
    reset_sent_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Wrong reset codes. At the limit the code is discarded, not the account locked:
    # an attacker guessing codes must not be able to lock a colleague out.
    reset_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base, UUIDPk, Timestamped):
    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 of the random token held in the client's cookie.
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)

    # True until the emailed code is accepted. A pending session grants NOTHING.
    otp_pending: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Argon2 hash of the outstanding code. Cleared on redemption, so a code is spent
    # exactly once even if the message is read twice.
    otp_code_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    otp_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the outstanding code was mailed. Backs the resend cooldown.
    otp_sent_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Wrong codes on this session. A 6-digit code is guessable in ~1M tries, so the
    # pending session is destroyed long before that is feasible.
    otp_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")
