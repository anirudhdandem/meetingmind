"""Create (or re-password) a MeetingMind account from the command line.

Anyone with an address inside INTERNAL_EMAIL_DOMAINS can sign up through the app, so
this script exists for the cases the signup form can't cover: seeding the very first
account before SMTP works, resetting a password for someone locked out, or minting an
account for an address outside those domains (`--force-domain`).

    python -m scripts.create_user                      # prompts for everything
    python -m scripts.create_user --email a@blostem.com --name "Ada"

Accounts made here are marked email-verified — the operator running this command is
already trusted more than an emailed code would prove. The user still gets a code at
every sign-in; that is the second factor, not an enrolment step.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.schemas.auth import MIN_PASSWORD_LEN


def _prompt_password() -> str:
    while True:
        pw = getpass.getpass("Password: ")
        if len(pw) < MIN_PASSWORD_LEN:
            print(f"  Too short — at least {MIN_PASSWORD_LEN} characters.", file=sys.stderr)
            continue
        if pw != getpass.getpass("Confirm password: "):
            print("  Passwords don't match.", file=sys.stderr)
            continue
        return pw


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a MeetingMind user.")
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument(
        "--force-domain",
        action="store_true",
        help="allow an email outside INTERNAL_EMAIL_DOMAINS",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.secret_key:
        sys.exit("SECRET_KEY is not set. Generate one with: openssl rand -hex 32")

    email = (args.email or input("Email: ")).strip().lower()
    domain = email.rsplit("@", 1)[-1]
    domains = settings.internal_email_domains or []
    if domains and domain not in domains and not args.force_domain:
        sys.exit(
            f"{email!r} is outside INTERNAL_EMAIL_DOMAINS ({', '.join(domains)}). "
            "Re-run with --force-domain if that's intended."
        )

    async with SessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalars().first()

        if existing is not None:
            print(f"{email} already exists.")
            if input("Reset their password? [y/N] ").strip().lower() != "y":
                return
            existing.password_hash = hash_password(_prompt_password())
            existing.failed_attempts = 0
            existing.locked_until = None
            await db.commit()
            print(f"Password reset for {email}.")
            return

        name = (args.name or input("Full name: ")).strip()
        if not name:
            sys.exit("A name is required.")

        db.add(
            User(
                email=email,
                name=name,
                password_hash=hash_password(_prompt_password()),
                email_verified=True,
            )
        )
        await db.commit()

    print(
        f"\nCreated {email}.\n"
        "Sign in at the frontend; a one-time code will be emailed to that address.\n"
        "With SMTP_HOST unset, the code is printed to the API server's log instead."
    )


if __name__ == "__main__":
    asyncio.run(main())
