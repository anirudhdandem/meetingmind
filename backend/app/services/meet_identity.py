"""Deterministic participant identity from the Meet REST API, via the bot's account.

The bot joins every meeting from one Google account. As a participant, that account
can read the finished meeting's conference record: every signed-in attendee comes
back with a stable user ID, which the People API resolves to a real email — provided
the bot account is on the internal Workspace domain (colleagues resolve through the
directory; external people usually don't, which is itself the answer).

Classification is therefore evidence-only:
  - resolved email on an internal domain  -> internal
  - resolved email on any other domain    -> client
  - signed-in but unresolvable / anonymous / phone -> no claim (left to other sources)

This is the strongest role source (above calendar emails and the name roster) and
involves no inference: an unregistered employee is classified correctly on their
very first call, and gets remembered in `team_members` (source="meet") after it.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.google import meet, oauth, people
from app.models.call import Call
from app.services.transcript_import import meeting_code_from_url

log = get_logger(__name__)

INTERNAL = "internal"
CLIENT = "client"

# The conference record can lag the meeting end by a little; the pipeline's batch
# transcription usually absorbs that, but retry briefly rather than lose the call.
_RECORD_ATTEMPTS = 3
_RECORD_RETRY_SECONDS = 20

# Match a record to the call by start time (same space can host many meetings).
_MAX_START_DRIFT = dt.timedelta(hours=6)


def _parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pick_record(records: list[dict], anchor: dt.datetime | None) -> dict | None:
    """The conference record closest in start time to the call (newest if unknown)."""
    if not records:
        return None
    if anchor is None:
        return records[0]  # API returns newest first
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=dt.timezone.utc)
    best, best_drift = None, _MAX_START_DRIFT
    for rec in records:
        start = _parse_time(rec.get("startTime"))
        if start is None:
            continue
        drift = abs(start - anchor)
        if drift <= best_drift:
            best, best_drift = rec, drift
    return best or records[0]


async def resolve_participants(session: AsyncSession, call: Call) -> list[dict]:
    """[{name, email, role}] for every signed-in participant we could identify.

    Empty when the bot account isn't connected (purpose="bot"), the call has no
    meeting code, no conference record matches, or the API errors — the caller then
    falls back to the other role sources. Never raises.
    """
    code = meeting_code_from_url(call.meeting_url or "")
    if not code:
        return []
    token = await oauth.access_token(session, oauth.BOT)
    if not token:
        return []

    s = get_settings()
    bot_email = (s.bot_google_account_email or "").strip().lower()
    domains = s.internal_email_domains or []

    try:
        record = None
        for attempt in range(_RECORD_ATTEMPTS):
            records = await meet.list_conference_records_by_code(token, code)
            record = _pick_record(records, call.started_at or call.created_at)
            if record:
                break
            if attempt < _RECORD_ATTEMPTS - 1:
                await asyncio.sleep(_RECORD_RETRY_SECONDS)
        if not record:
            log.warning("No conference record found for call %s (code %s)", call.id, code)
            return []

        participants = await meet.list_participants(token, record["name"])
    except Exception:
        log.exception("Meet participant lookup failed for call %s", call.id)
        return []

    resolved: list[dict] = []
    for p in participants:
        signed_in = p.get("signedinUser")
        if not signed_in:
            continue  # anonymous / phone: no identity claim
        display_name = (signed_in.get("displayName") or "").strip()
        try:
            person = await people.resolve_person(token, signed_in.get("user") or "")
        except Exception:
            log.exception(
                "People lookup failed for participant %r on call %s", display_name, call.id
            )
            person = None
        if not person:
            continue  # not visible to us: not provably internal, make no claim
        email = person["email"]
        if email == bot_email:
            continue  # the bot itself
        domain = email.rsplit("@", 1)[-1]
        role = INTERNAL if domain in domains else CLIENT
        resolved.append({"name": display_name or person.get("name") or "", "email": email, "role": role})

    log.info(
        "Meet identity for call %s: %d participants, %d resolved (%s)",
        call.id,
        len(participants),
        len(resolved),
        {r["name"]: r["role"] for r in resolved},
    )
    return resolved
