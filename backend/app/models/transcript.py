"""ORM model: call_transcripts — live diarized chunks (spec step 3)."""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class CallTranscript(Base, UUIDPk, Timestamped):
    __tablename__ = "call_transcripts"

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), index=True
    )
    # Deepgram diarization index (anonymous: "0", "1", ...). Name mapping is a later concern.
    speaker_label: Mapped[str | None] = mapped_column(String, nullable=True)
    # Who this segment belongs to: "internal" (our team), "client", or "unknown".
    # Set post-attribution by matching the resolved speaker name to the calendar
    # event's attendee emails (internal_email_domains). NULL = not yet computed.
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_ts: Mapped[float] = mapped_column(Float, nullable=False)  # seconds from call start
    end_ts: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
