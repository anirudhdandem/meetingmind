"""ORM model: calls — per-call metadata (spec step 4)."""

import datetime
import enum
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class CallStatus(str, enum.Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class MeetingPlatform(str, enum.Enum):
    meet = "meet"
    zoom = "zoom"
    teams = "teams"


class Call(Base, UUIDPk, Timestamped):
    __tablename__ = "calls"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    sales_rep_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # The app user who started this call by hand (paste-a-link / scheduled form).
    # NULL for auto-joined calls — those are scoped to viewers via the linked
    # calendar event's attendee_emails instead — and for pre-ownership rows,
    # which stay visible to everyone.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    meeting_platform: Mapped[MeetingPlatform] = mapped_column(
        Enum(MeetingPlatform, name="meeting_platform"), default=MeetingPlatform.meet
    )
    meeting_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # The LiveKit room the bot publishes captured audio into; links the webhook back to the call.
    livekit_room: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Real participant names read from the Meet roster (used as MOM attendees).
    participants: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    scheduled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus, name="call_status"), default=CallStatus.scheduled, index=True
    )
