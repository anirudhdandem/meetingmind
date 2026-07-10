"""Request/response schemas for the auth routes."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

# Long enough that Argon2, not the keyspace, is the attacker's bottleneck.
# Enforced identically here and in `scripts.create_user`.
MIN_PASSWORD_LEN = 12


class SignupIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=MIN_PASSWORD_LEN, max_length=256)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginOut(BaseModel):
    """What the client needs to render the next step.

    Signup and login return the same shape, because they end in the same place: the
    session cookie is set, a code is in the user's inbox, and all that's left is to
    post it back.
    """

    # Where the code went, echoed so the UI can say "we mailed you@blostem.com".
    email: str
    name: str
    # Seconds the client must wait before offering "Resend".
    resend_after_seconds: int


class OtpVerifyIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class MeOut(BaseModel):
    id: str
    email: str
    name: str
    email_verified: bool
    # True when the password was accepted but the emailed code hasn't been entered yet.
    otp_pending: bool


class ResendOut(BaseModel):
    resend_after_seconds: int


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=MIN_PASSWORD_LEN, max_length=256)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ForgotPasswordOut(BaseModel):
    # Seconds before another code may be requested for this address.
    resend_after_seconds: int


class ResetPasswordIn(BaseModel):
    # The address is carried here rather than in a cookie: a reset is anonymous, and
    # the code is deliberately redeemable from a different browser than requested it.
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)
    new_password: str = Field(min_length=MIN_PASSWORD_LEN, max_length=256)
