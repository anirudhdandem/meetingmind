"""Calendar auto-join: put the bot in every meeting it's invited to, unprompted.

How Fireflies/Otter/Read.ai do it, and how this does it: the bot's email address
is added to the meeting invite (users already do this — it's what gets the bot
auto-admitted), which places the event on the bot account's own Google Calendar.
A background poller reads that calendar through the "bot" OAuth connection and
launches a recording bot as each meeting starts. Nobody pastes a link.

A user-connected calendar (the "calendar" OAuth purpose) is swept the same way:
every Meet-bearing event on it is joined too, invite or not. The difference is
admission — an uninvited bot knocks and waits in Meet's lobby, giving up after
`bot_admit_timeout_seconds` (cancelled meeting / nobody showed), while an
invited one walks straight in. Both calendars can list the same event; the
upsert (same google_event_id) and the adopt-by-meet-code check at dispatch
keep it to one bot per meeting.

The loop each tick:
  1. Mirror upcoming events (with a Meet link) into `calendar_events` — one row
     per occurrence, upserted by google_event_id, tracking reschedules and
     cancellations.
  2. Dispatch every pending event whose start time is within the join lead:
     create a Call (same shape as the manual /calls/start flow) and hand it to
     the bot manager. If someone already started a bot for that meeting by hand,
     adopt their call instead of joining twice.

State lives in the DB, so restarts never double-join; capacity is re-checked
every tick, so a full house just delays a join instead of dropping it.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.google import calendar, oauth
from app.models import calendar_event as ce
from app.models.calendar_event import CalendarEvent
from app.models.call import Call, CallStatus, MeetingPlatform
from app.services.participant_roles import _event_meet_code

log = get_logger(__name__)

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

# How far back the sync window reaches, so an event that already started (or a
# poller that was down briefly) is still picked up mid-meeting.
_SYNC_LOOKBACK = dt.timedelta(minutes=30)
# A manual bot for the same Meet code within this window counts as "already
# recording this meeting" and is adopted instead of double-joining.
_ADOPT_WINDOW = dt.timedelta(hours=4)

# Log the "reconnect to grant calendar access" hint once, not every minute.
_warned_no_scope = False


def _parse_ts(value: str | None) -> dt.datetime | None:
    """RFC3339 timestamp (Google uses a trailing 'Z') -> aware datetime."""
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _bot_declined(event: dict, owner_email: str) -> bool:
    """True when the calendar owner's own invite was declined — the human way to say
    'don't join'. On the bot's calendar the owner is the bot; on a user-connected
    calendar it's the user, so declining a meeting also declines the recording."""
    for a in event.get("attendees") or []:
        if a.get("self") or (a.get("email") or "").strip().lower() == owner_email:
            return a.get("responseStatus") == "declined"
    return False


def _meeting_url(event: dict, code: str) -> str:
    for ep in (event.get("conferenceData") or {}).get("entryPoints") or []:
        uri = ep.get("uri") or ""
        if code in uri:
            return uri
    return event.get("hangoutLink") or f"https://meet.google.com/{code}"


async def _sync_events(db: AsyncSession, events: list[dict], owner_email: str) -> None:
    """Mirror the calendar window into calendar_events (upsert by google_event_id)."""
    now = dt.datetime.now(dt.timezone.utc)
    for event in events:
        event_id = event.get("id")
        start = _parse_ts((event.get("start") or {}).get("dateTime"))
        if not event_id or start is None:  # all-day events carry no dateTime
            continue
        code = _event_meet_code(event)
        if not code:  # no Meet link — nothing to join
            continue
        end = _parse_ts((event.get("end") or {}).get("dateTime"))

        row = (
            await db.execute(
                select(CalendarEvent).where(CalendarEvent.google_event_id == event_id)
            )
        ).scalars().first()
        if row is None:
            row = CalendarEvent(
                google_event_id=event_id,
                meet_code=code,
                meeting_url=_meeting_url(event, code),
                start_at=start,
                end_at=end,
            )
            db.add(row)

        row.meet_code = code
        row.meeting_url = _meeting_url(event, code)
        row.title = event.get("summary") or row.title
        row.organizer_email = (event.get("organizer") or {}).get("email") or row.organizer_email
        rescheduled = row.start_at != start
        row.start_at = start
        row.end_at = end

        if row.status == ce.DISPATCHED:
            continue  # a bot is already in (or was in) this meeting — leave it be
        if event.get("status") == "cancelled":
            row.status, row.note = ce.CANCELLED, "event cancelled on the calendar"
        elif _bot_declined(event, owner_email):
            row.status, row.note = ce.SKIPPED, "bot's invite was declined"
        elif row.status in (ce.CANCELLED, ce.SKIPPED):
            # No longer cancelled / no longer declined: back on the schedule.
            row.status, row.note = ce.PENDING, None
        elif row.status == ce.MISSED and rescheduled and start > now:
            # A missed meeting rescheduled into the future gets another shot.
            row.status, row.note = ce.PENDING, None
    await db.commit()


async def _adopt_existing_call(db: AsyncSession, row: CalendarEvent) -> bool:
    """Link the event to a bot someone already started by hand for the same meeting."""
    since = dt.datetime.now(dt.timezone.utc) - _ADOPT_WINDOW
    existing = (
        await db.execute(
            select(Call)
            .where(
                Call.status.in_((CallStatus.scheduled, CallStatus.in_progress)),
                Call.meeting_url.contains(row.meet_code),
                Call.created_at >= since,
            )
            .order_by(Call.created_at.desc())
        )
    ).scalars().first()
    if existing is None:
        return False
    row.status, row.call_id = ce.DISPATCHED, existing.id
    row.note = "adopted a manually started recording"
    log.info("auto-join: %s already being recorded (call %s)", row.meet_code, existing.id)
    return True


async def _dispatch_due(db: AsyncSession) -> None:
    """Launch a bot for every pending event whose start time has arrived."""
    from app.api.routes.calls import DEFAULT_COMPANY_NAME, _get_or_create_company
    from app.bot import manager

    settings = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    due_at = now + dt.timedelta(seconds=settings.auto_join_lead_seconds)

    rows = (
        await db.execute(
            select(CalendarEvent)
            .where(CalendarEvent.status == ce.PENDING, CalendarEvent.start_at <= due_at)
            .order_by(CalendarEvent.start_at)
        )
    ).scalars().all()

    for row in rows:
        if row.end_at is not None and row.end_at <= now:
            row.status, row.note = ce.MISSED, "meeting ended before a bot could join"
            await db.commit()
            continue
        if await _adopt_existing_call(db, row):
            await db.commit()
            continue
        if not manager.has_capacity():
            # Leave it pending: a slot may free up before the meeting ends, and
            # the next tick will retry.
            log.warning(
                "auto-join: all %s bot slots busy — %r (%s) waits",
                settings.max_concurrent_bots, row.title, row.meet_code,
            )
            break

        company = await _get_or_create_company(db, DEFAULT_COMPANY_NAME)
        call = Call(
            company_id=company.id,
            meeting_platform=MeetingPlatform.meet,
            meeting_url=row.meeting_url,
            scheduled_at=row.start_at,
            livekit_room=f"mm-{uuid.uuid4().hex[:12]}",
            status=CallStatus.scheduled,
        )
        db.add(call)
        await db.flush()
        row.status, row.call_id, row.note = ce.DISPATCHED, call.id, None
        # Commit BEFORE launching: the bot task reads the call from its own session.
        await db.commit()
        try:
            manager.start_bot(call.id)
        except RuntimeError:  # lost a capacity race with a manual start
            row.status, row.call_id = ce.PENDING, None
            await db.commit()
            break
        log.info(
            "auto-join: launched bot for %r (%s) starting %s -> call %s",
            row.title, row.meet_code, row.start_at.isoformat(), call.id,
        )


async def tick() -> None:
    """One poll cycle: read every connected calendar, sync the mirror, dispatch what's due.

    Two sources feed the schedule: the bot's own calendar (meetings it was invited
    to — auto-admitted) and the user-connected calendar (all their meetings — the
    bot knocks). Either alone is enough; both together dedupe via the upsert.
    """
    global _warned_no_scope
    settings = get_settings()
    if not oauth.is_configured():
        return

    async with SessionLocal() as db:
        now = dt.datetime.now(dt.timezone.utc)
        window = (
            (now - _SYNC_LOOKBACK).isoformat(),
            (now + dt.timedelta(hours=settings.auto_join_lookahead_hours)).isoformat(),
        )

        synced_any = False
        for purpose in (oauth.BOT, oauth.CALENDAR):
            cred = await oauth.connected_account(db, purpose)
            if cred is None:
                continue  # not connected — Settings page does that
            if cred.scopes and CALENDAR_SCOPE not in cred.scopes:
                # Only the bot connection can legitimately lack the scope (it predates
                # auto-join); the calendar purpose exists solely to grant it.
                if purpose == oauth.BOT and not _warned_no_scope:
                    log.warning(
                        "auto-join: the connected bot account (%s) has no calendar access — "
                        "reconnect it in Settings to grant calendar.readonly",
                        cred.email,
                    )
                    _warned_no_scope = True
                continue
            if purpose == oauth.BOT:
                _warned_no_scope = False

            token = await oauth.access_token(db, purpose)
            if not token:
                continue
            events = await calendar.list_events(token, *window, show_deleted=True)
            await _sync_events(db, events, cred.email)
            synced_any = True

        if synced_any:
            await _dispatch_due(db)


async def run_loop(stop: asyncio.Event) -> None:
    """Poll until `stop` is set. Errors are logged and the loop keeps going."""
    settings = get_settings()
    log.info(
        "calendar auto-join poller running (every %ss, join lead %ss)",
        settings.auto_join_poll_seconds, settings.auto_join_lead_seconds,
    )
    while not stop.is_set():
        try:
            await tick()
        except Exception:
            log.exception("auto-join tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.auto_join_poll_seconds)
        except asyncio.TimeoutError:
            pass
