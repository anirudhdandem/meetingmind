"""Thin async client for the Google Calendar REST API (v3).

Used to recover participant *emails* for a call: the bot only scrapes display names
from the Meet roster, but the meeting's calendar event carries `attendees[].email` —
which lets us classify each speaker as our internal team vs the client by domain.

Auth-agnostic: callers pass an access token (minted from the per-user OAuth flow in
app.google.oauth). Docs: https://developers.google.com/calendar/api/v3/reference/events/list
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

BASE = "https://www.googleapis.com/calendar/v3"


async def list_events(
    access_token: str, time_min: str, time_max: str, *, show_deleted: bool = False
) -> list[dict]:
    """Events on the token owner's primary calendar within [time_min, time_max].

    Both bounds are RFC3339 timestamps. `singleEvents` expands recurring events so
    each occurrence carries its own conference data / attendees. `show_deleted`
    includes cancelled events (status="cancelled") — the auto-join poller needs
    them to un-schedule a bot when a meeting is cancelled.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE}/calendars/primary/events",
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 100,
                "showDeleted": "true" if show_deleted else "false",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        return r.json().get("items", [])
