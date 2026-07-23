"""Outbound mail. Exactly one thing is sent from here: the sign-in code.

`smtplib` is synchronous and blocking, so every send is pushed to a worker thread —
a stalled SMTP handshake would otherwise freeze the whole event loop, and Gmail's
handshake is not fast. The alternative (an async SMTP client) buys nothing here: the
API sends one short message per login, not a campaign.

With SMTP_HOST unset the code is written to the log instead of mailed. That is what
makes a fresh clone runnable — sign up, read the code off the server output, get in —
and it is why `_check_production_safety` refuses to boot a production server without
SMTP configured. A deployment that silently logged codes would be handing every
operator with journal access a skeleton key.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class EmailDeliveryError(RuntimeError):
    """The message could not be handed to the SMTP server."""


def _build(to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = get_settings().smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def _send_blocking(msg: EmailMessage) -> None:
    s = get_settings()
    # Port 465 speaks TLS from the first byte; 587 (and everything else) opens in the
    # clear and upgrades with STARTTLS. Getting this backwards hangs until timeout
    # rather than failing cleanly, so branch on the port rather than guessing.
    if s.smtp_port == 465:
        client = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20)
    else:
        client = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
    with client:
        if s.smtp_port != 465:
            client.starttls()
        if s.smtp_user and s.smtp_pass:
            client.login(s.smtp_user, s.smtp_pass)
        client.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> None:
    """Deliver one message, or raise EmailDeliveryError.

    Callers must let the failure reach the user: a sign-in code that was never sent
    is indistinguishable, from the login form, from one the user simply hasn't typed
    yet, and they would sit waiting for mail that is not coming.
    """
    s = get_settings()

    if not s.smtp_host:
        log.warning("SMTP not configured — %r to %s:\n%s", subject, to, body)
        return

    try:
        await asyncio.to_thread(_send_blocking, _build(to, subject, body))
    except (smtplib.SMTPException, OSError) as exc:
        log.error("SMTP send to %s failed: %s", to, exc)
        raise EmailDeliveryError(str(exc)) from exc

    log.info("Sent %r to %s", subject, to)


async def send_login_code(to: str, name: str, code: str, *, ttl_minutes: int) -> None:
    """Mail a sign-in code. The code appears in the subject so it's readable from a
    notification banner without opening the message."""
    await send_email(
        to,
        f"{code} is your Fennec sign-in code",
        (
            f"Hi {name},\n\n"
            f"Your Fennec sign-in code is:\n\n"
            f"    {code}\n\n"
            f"It expires in {ttl_minutes} minutes and can only be used once.\n\n"
            "If you didn't try to sign in, someone else knows your password. "
            "Change it as soon as you can.\n"
        ),
    )


async def send_password_reset_code(to: str, name: str, code: str, *, ttl_minutes: int) -> None:
    """Mail a password-reset code.

    Worded so an unexpected message reads as a warning rather than an instruction —
    this is the one mail a phisher would most like us to send on their behalf.
    """
    await send_email(
        to,
        f"{code} is your Fennec password reset code",
        (
            f"Hi {name},\n\n"
            f"Someone asked to reset the password on your Fennec account. "
            f"Your reset code is:\n\n"
            f"    {code}\n\n"
            f"It expires in {ttl_minutes} minutes and can only be used once.\n\n"
            "If that wasn't you, ignore this email — your password has not changed, "
            "and nobody can change it without this code.\n"
        ),
    )
