"""ORM model: calendar_events — meetings discovered on the bot's own calendar.

Auto-join works the way Fireflies/Otter do: users invite the bot's email to the
meeting, so the event (with its Meet link) lands on the bot account's Google
Calendar. The auto-join poller mirrors upcoming events into this table and
dispatches a bot when each one starts. One row per event occurrence is the
dedupe that stops the same meeting from being joined twice — across poll ticks
and across server restarts.
"""

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk

# Lifecycle of a discovered event. Plain strings (not a PG enum) so adding a
# state never needs a migration.
PENDING = "pending"        # seen on the calendar, waiting for its start time
DISPATCHED = "dispatched"  # a bot was launched (or an existing call adopted)
MISSED = "missed"          # start+end passed without capacity/opportunity to join
SKIPPED = "skipped"        # deliberately not joined (bot declined the invite)
CANCELLED = "cancelled"    # the event was cancelled on the calendar


class CalendarEvent(Base, UUIDPk, Timestamped):
    __tablename__ = "calendar_events"

    # Google's event id; with singleEvents=true each occurrence of a recurring
    # meeting gets its own id, so recurring meetings dedupe per-occurrence.
    google_event_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    # The Meet meeting code (abc-mnop-xyz) and full join URL from the event.
    meet_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    meeting_url: Mapped[str] = mapped_column(String, nullable=False)

    title: Mapped[str | None] = mapped_column(String, nullable=True)
    organizer_email: Mapped[str | None] = mapped_column(String, nullable=True)

    start_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(
        String, nullable=False, default=PENDING, server_default=PENDING, index=True
    )
    # Why the event ended up skipped/missed/adopted — shown in the UI schedule.
    note: Mapped[str | None] = mapped_column(String, nullable=True)

    # The call the dispatched bot records into (kept if the call is deleted-safe).
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True
    )
