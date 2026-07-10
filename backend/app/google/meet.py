"""Thin async client for the Google Meet REST API (v2).

Flow to get a finished meeting's transcript:
  get_space(code) -> list_conference_records(space) -> list_transcripts(cr)
  -> list_transcript_entries(transcript)

Docs: https://developers.google.com/workspace/meet/api/guides/artifacts
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger
from app.google.auth import get_access_token

log = get_logger(__name__)

BASE = "https://meet.googleapis.com/v2"


async def _get(path: str, params: dict | None = None, subject: str | None = None) -> dict:
    token = await get_access_token(subject)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE}/{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json()


async def get_space(meeting_code: str, subject: str | None = None) -> dict:
    """Resolve a Meet meeting code (e.g. 'abc-mnop-xyz') to a space resource."""
    return await _get(f"spaces/{meeting_code}", subject=subject)


async def list_conference_records(space_name: str, subject: str | None = None) -> list[dict]:
    """All conference sessions held in a space (space_name = 'spaces/...')."""
    data = await _get(
        "conferenceRecords",
        params={"filter": f'space.name="{space_name}"'},
        subject=subject,
    )
    return data.get("conferenceRecords", [])


async def list_transcripts(conference_record: str, subject: str | None = None) -> list[dict]:
    """Transcripts for a conference (conference_record = 'conferenceRecords/...')."""
    data = await _get(f"{conference_record}/transcripts", subject=subject)
    return data.get("transcripts", [])


async def list_transcript_entries(transcript_name: str, subject: str | None = None) -> list[dict]:
    """All entries (speaker + text + timestamps) for a transcript, paged."""
    entries: list[dict] = []
    page_token: str | None = None
    while True:
        params: dict = {"pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        data = await _get(f"{transcript_name}/entries", params=params, subject=subject)
        entries.extend(data.get("transcriptEntries", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return entries


# --- Token-based access (the bot's own OAuth token, no service account) --------
# The bot account is a PARTICIPANT of every meeting it records, which is enough to
# read that meeting's conference record and participant list.

async def _get_with_token(access_token: str, path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE}/{path}",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        return r.json()


async def list_conference_records_by_code(access_token: str, meeting_code: str) -> list[dict]:
    """Conference records for a Meet meeting code, newest first."""
    data = await _get_with_token(
        access_token,
        "conferenceRecords",
        params={"filter": f'space.meeting_code = "{meeting_code}"'},
    )
    return data.get("conferenceRecords", [])


async def list_participants(access_token: str, conference_record: str) -> list[dict]:
    """All participants of a conference (conference_record = 'conferenceRecords/...'), paged.

    Each item is one of signedinUser (user id + displayName), anonymousUser
    (displayName only), or phoneUser.
    """
    participants: list[dict] = []
    page_token: str | None = None
    while True:
        params: dict = {"pageSize": 100}
        if page_token:
            params["pageToken"] = page_token
        data = await _get_with_token(
            access_token, f"{conference_record}/participants", params=params
        )
        participants.extend(data.get("participants", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return participants
