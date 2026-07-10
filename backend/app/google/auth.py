"""Google service-account auth with domain-wide delegation.

The service account impersonates a Workspace user (the meeting organizer) so we
can read their Meet conference records / transcripts (and calendar) over the
REST API — no browser, no password, no 2FA.

Setup the Workspace admin must do once:
  * Admin Console > Security > Access and data control > API Controls >
    Domain-wide Delegation > add the service account's client ID with the
    SCOPES below.
  * Enable Meet transcription (and/or recording) for the org/OU, so artifacts
    actually get produced.
"""

from __future__ import annotations

import asyncio

from google.auth.transport.requests import Request
from google.oauth2 import service_account

from app.config import get_settings

# Read-only: conference records/transcripts, Drive (artifact download), calendar.
SCOPES = [
    "https://www.googleapis.com/auth/meetings.space.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def _build_credentials(subject: str) -> service_account.Credentials:
    s = get_settings()
    if not s.google_service_account_file:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE is not set")
    return service_account.Credentials.from_service_account_file(
        s.google_service_account_file, scopes=SCOPES, subject=subject
    )


async def get_access_token(subject: str | None = None) -> str:
    """Mint a short-lived access token for the impersonated user.

    google-auth is sync, so the refresh runs in a thread to stay async-friendly.
    """
    s = get_settings()
    subject = subject or s.google_impersonate_subject
    if not subject:
        raise RuntimeError("GOOGLE_IMPERSONATE_SUBJECT is not set")

    def _refresh() -> str:
        creds = _build_credentials(subject)
        creds.refresh(Request())
        return creds.token

    return await asyncio.to_thread(_refresh)
