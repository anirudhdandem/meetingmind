"""Classify each speaker as our internal team vs the client — deterministically.

The bot records one mixed stream and only knows speakers by display NAME. Roles
feed the performance metrics, so classification must be EVIDENCE-based; the LLM
never decides a role. Sources, in priority order:

  1. **Meet participant identity** (services/meet_identity.py): the bot's own
     account reads the finished meeting's participant list and resolves signed-in
     attendees to real emails via the People API. Strongest — verified identity,
     works for any employee with zero registration.
  2. **Calendar emails** (if a Google calendar is connected via OAuth): match the
     call to its calendar event, read `attendees[].email`, classify by domain
     (internal_email_domains).
  3. **Internal-team roster** (`team_members`): a speaker whose name matches an
     active roster member is internal. The roster grows itself from source 1
     (email-verified internals are persisted with source="meet"), and covers the
     rare cases identity can't: people who join anonymously or dial in by phone.

A speaker we couldn't name (bare diarization index) is unknown. If we have NO signal
at all (no identities, no calendar, empty roster), roles are left unset rather than
guessed.
"""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.google import calendar, oauth
from app.models.call import Call
from app.models.team import TeamMember
from app.services.transcript_import import meeting_code_from_url

log = get_logger(__name__)

INTERNAL = "internal"
CLIENT = "client"
UNKNOWN = "unknown"

# How far either side of the call time to search the calendar for its event.
_SEARCH_WINDOW = dt.timedelta(days=1)


def _norm(name: str) -> str:
    """Loose key for matching names across sources (roster / calendar / transcript)."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


# --- Source 1: calendar emails ------------------------------------------------

def classify_email(email: str, domains: list[str]) -> str:
    """internal if the email's domain is one of ours, else client."""
    domain = (email or "").rsplit("@", 1)[-1].strip().lower()
    return INTERNAL if domain and domain in domains else CLIENT


def _event_meet_code(event: dict) -> str | None:
    """The Meet meeting code (abc-mnop-xyz) for a calendar event, if it has one."""
    code = meeting_code_from_url(event.get("hangoutLink") or "")
    if code:
        return code
    for ep in (event.get("conferenceData") or {}).get("entryPoints") or []:
        code = meeting_code_from_url(ep.get("uri") or "")
        if code:
            return code
    return None


async def build_email_roles(session: AsyncSession, call: Call) -> dict[str, str]:
    """{normalized attendee name -> role} from the call's calendar event, or {}.

    Empty when no calendar is connected, the call has no Meet code, or no event
    matches — the caller then leans on the roster instead.
    """
    if not oauth.is_configured():
        return {}
    code = meeting_code_from_url(call.meeting_url or "")
    if not code:
        return {}
    token = await oauth.access_token(session)
    if not token:
        return {}

    anchor = call.scheduled_at or call.started_at or call.created_at
    if anchor is None:
        return {}
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=dt.timezone.utc)
    time_min = (anchor - _SEARCH_WINDOW).isoformat()
    time_max = (anchor + _SEARCH_WINDOW).isoformat()

    try:
        events = await calendar.list_events(token, time_min, time_max)
    except Exception:
        log.exception("Calendar lookup failed for call %s", call.id)
        return {}

    event = next((e for e in events if _event_meet_code(e) == code), None)
    if event is None:
        log.info("No calendar event matched Meet code %s for call %s", code, call.id)
        return {}

    domains = get_settings().internal_email_domains or []
    roles: dict[str, str] = {}
    for a in event.get("attendees") or []:
        if a.get("resource"):  # meeting rooms / equipment, not people
            continue
        email = a.get("email") or ""
        role = classify_email(email, domains)
        if a.get("displayName"):
            roles[_norm(a["displayName"])] = role
        local = email.rsplit("@", 1)[0]
        if local:
            roles.setdefault(_norm(local), role)  # fall back to the email handle
    if roles:
        log.info("Calendar role map for call %s (code %s): %s", call.id, code, roles)
    return roles


# --- Source 2: internal-team roster -------------------------------------------

async def load_internal_names(session: AsyncSession) -> set[str]:
    """Normalized names of every active team member — the set of "us"."""
    rows = (
        await session.execute(select(TeamMember).where(TeamMember.active.is_(True)))
    ).scalars().all()
    return {_norm(m.name) for m in rows if m.name}


# --- Source 1: Meet participant identity (email-verified) ---------------------

def meet_role_map(resolved: list[dict]) -> dict[str, str]:
    """{normalized display name -> role} from email-verified Meet participants."""
    out: dict[str, str] = {}
    for r in resolved or []:
        key = _norm(r.get("name") or "")
        role = r.get("role")
        if key and role in (INTERNAL, CLIENT):
            out[key] = role
    return out


async def auto_register_internal(
    session: AsyncSession, entries: list[tuple[str, str | None]], source: str
) -> list[str]:
    """Persist newly-learned internal members as (name, email) rows. Returns names added.

    Only called with EVIDENCE-backed entries: email-verified Meet participants
    (source="meet") or attendees of a user-declared internal meeting (source="auto").
    Dedupes against EVERY existing row, active or not — a member the user deactivated
    was a deliberate correction and must not be re-learned.
    """
    entries = [e for e in entries if e and e[0]]
    if not entries:
        return []
    existing = {
        _norm(m.name)
        for m in (await session.execute(select(TeamMember))).scalars().all()
        if m.name
    }
    added: list[str] = []
    for name, email in entries:
        key = _norm(name)
        if not key or key in existing:
            continue
        session.add(TeamMember(name=name, email=email, source=source))
        existing.add(key)
        added.append(name)
    if added:
        await session.flush()
        log.info("Auto-registered internal team members (%s): %s", source, added)
    return added


# --- Combined classification --------------------------------------------------

def has_signal(
    internal_names: set[str],
    email_roles: dict[str, str],
    meet_roles: dict[str, str] | None = None,
) -> bool:
    """Whether we have any basis to classify (identity, calendar, or roster)."""
    return bool(internal_names or email_roles or meet_roles)


def role_for(
    speaker_label: str | None,
    internal_names: set[str],
    email_roles: dict[str, str],
    meet_roles: dict[str, str] | None = None,
) -> str:
    """Role for a segment. Precedence: Meet identity > calendar emails > roster.

    A named speaker no source covers defaults to 'client' — reached only when SOME
    signal existed (the caller gates on has_signal). With Meet identity active every
    signed-in attendee is resolved, so that fallback correctly means "not one of the
    identified internals".
    """
    if not speaker_label or str(speaker_label).isdigit():
        return UNKNOWN
    key = _norm(speaker_label)
    if meet_roles and key in meet_roles:
        return meet_roles[key]
    if key in email_roles:
        return email_roles[key]
    if key in internal_names:
        return INTERNAL
    return CLIENT


def sides_from_roster(
    roster: list[str],
    internal_names: set[str],
    email_roles: dict[str, str],
    meet_roles: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """Split roster names into {"internal": [...], "client": [...]} for the LLM prompt."""
    sides: dict[str, list[str]] = {INTERNAL: [], CLIENT: []}
    for name in roster:
        role = role_for(name, internal_names, email_roles, meet_roles)
        if role in (INTERNAL, CLIENT):
            sides[role].append(name)
    return sides
