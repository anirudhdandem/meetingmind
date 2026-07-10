"""Cryptographic primitives for app login: passwords, sessions, one-time codes.

Every function here is deliberately boring. The interesting decisions:

* **Argon2id** for passwords and one-time codes — memory-hard, so a stolen hash costs
  a GPU attacker real RAM per guess. A 6-digit code has only a million possibilities,
  which a fast hash would exhaust in seconds against a leaked database.
* **Session tokens are random, not derived.** 256 bits from `secrets`, SHA-256'd before
  storage. SHA-256 (not Argon2) is correct here precisely because the input is already
  high-entropy: there is nothing to brute-force, and a session lookup happens on every
  request. Argon2 would buy nothing and cost ~100ms per request.
* **One-time codes are hashed, never stored in the clear.** Verification only ever asks
  "does this match", so there is no reason to keep a form that a database dump could
  replay before it expires.
* **Constant-time comparison** wherever a secret is checked, so response timing does
  not leak how much of a value was correct.
"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


# --- Passwords ----------------------------------------------------------------


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True if the password matches. Never raises on a bad or malformed hash."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the hash predates the current Argon2 parameters (rehash on next login)."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


# --- Session tokens -----------------------------------------------------------


def new_session_token() -> str:
    """A fresh 256-bit session token. Returned to the client exactly once."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """The stored form of a session token. Fast by design — see module docstring."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- Email one-time codes -----------------------------------------------------


def new_otp_code(length: int = 6) -> str:
    """A uniformly random numeric code, leading zeros preserved.

    `randbelow` over the whole range rather than digit-by-digit choice: both are
    unbiased, but this makes the size of the keyspace (10**length) obvious.
    """
    if length < 4:
        raise ValueError("An OTP shorter than 4 digits is guessable by hand")
    return str(secrets.randbelow(10**length)).zfill(length)


def normalize_otp_code(code: str) -> str:
    """Canonical form for comparison. Codes get pasted out of mail clients with stray
    spaces, and some clients insert a non-breaking space when the line wraps."""
    return (code or "").strip().replace(" ", "").replace(" ", "")


def hash_otp_code(code: str) -> str:
    return _hasher.hash(normalize_otp_code(code))


def verify_otp_code(code: str, code_hash: str) -> bool:
    """True if the code matches. Argon2's own comparison is constant-time."""
    code = normalize_otp_code(code)
    if not code.isdigit():
        return False
    return verify_password(code, code_hash)
