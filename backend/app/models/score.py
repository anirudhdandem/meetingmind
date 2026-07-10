"""ORM model: call_scores — rubric scores (spec step 8)."""

import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class CallScore(Base, UUIDPk, Timestamped):
    __tablename__ = "call_scores"

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), index=True
    )

    # All scores on a 0-100 scale for comparable deltas in the comparison step.
    engagement_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    objection_severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    urgency_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    technical_fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qualitative_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
