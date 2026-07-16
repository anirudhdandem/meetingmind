"""Who may see which meeting — the rules behind the per-user dashboard.

A user's dashboard shows only THEIR meetings: ones they started by hand, and
ones whose calendar invite lists one of their email addresses (their app login
or any Google account they've connected). Rows written before ownership existed
carry no signal at all, and those deliberately stay visible to everyone —
hiding the team's entire history on deploy would be worse than the bug.

The matching is by email, not by "whose calendar sweep found the event": the
same invite lands on every attendee's calendar, so a meeting both Animesh and
Mitesh attended is (correctly) visible to both.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call import Call
from app.models.calendar_event import CalendarEvent
from app.models.google_oauth import GoogleOAuthCredential
from app.models.user import User

# Sentinel distinguishing "call has no linked calendar event" from "linked event
# recorded no attendees" — the former may still be owned via created_by_user_id.
_NO_EVENT = object()


async def user_emails(db: AsyncSession, user: User) -> set[str]:
    """Every address that identifies this user: app login + connected Google accounts."""
    emails = {user.email.strip().lower()}
    rows = (
        await db.execute(
            select(GoogleOAuthCredential.email).where(
                GoogleOAuthCredential.user_id == user.id
            )
        )
    ).scalars().all()
    emails.update(e.strip().lower() for e in rows if e)
    return emails


def call_visible(
    call: Call, event_attendees: object, emails: set[str], user_id: uuid.UUID
) -> bool:
    """`event_attendees` is the linked event's attendee_emails (list | None) or
    `_NO_EVENT` when the call has no calendar event at all."""
    if call.created_by_user_id == user_id:
        return True
    if event_attendees is not _NO_EVENT and event_attendees:
        return any((e or "").lower() in emails for e in event_attendees)
    # No ownership signal (pre-ownership row, or an event synced before attendee
    # tracking): legacy data, visible to the whole team. A call another user
    # explicitly started stays theirs alone.
    return call.created_by_user_id is None


def event_visible(attendee_emails: list | None, emails: set[str]) -> bool:
    if not attendee_emails:  # synced before attendee tracking — legacy, show it
        return True
    return any((e or "").lower() in emails for e in attendee_emails)


async def attendees_by_call(db: AsyncSession, call_ids: list[uuid.UUID]) -> dict:
    """call_id -> the linked calendar event's attendee_emails, for calls that have one."""
    if not call_ids:
        return {}
    rows = (
        await db.execute(
            select(CalendarEvent.call_id, CalendarEvent.attendee_emails).where(
                CalendarEvent.call_id.in_(call_ids)
            )
        )
    ).all()
    return {call_id: attendees for call_id, attendees in rows}


async def visible_calls(db: AsyncSession, calls: list[Call], user: User) -> list[Call]:
    """Filter a call list down to what `user` may see, preserving order."""
    emails = await user_emails(db, user)
    by_call = await attendees_by_call(db, [c.id for c in calls])
    return [
        c for c in calls if call_visible(c, by_call.get(c.id, _NO_EVENT), emails, user.id)
    ]


async def ensure_call_visible(db: AsyncSession, call: Call, user: User) -> bool:
    """Single-call variant for the /calls/{id} detail routes."""
    return bool(await visible_calls(db, [call], user))
