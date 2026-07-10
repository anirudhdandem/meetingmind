"""ORM model: lead_outcomes — won/lost ground truth (spec step 9)."""

import datetime
import enum
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class OutcomeStatus(str, enum.Enum):
    accepted = "accepted"
    rejected = "rejected"
    pending = "pending"


class LeadOutcome(Base, UUIDPk, Timestamped):
    __tablename__ = "lead_outcomes"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[OutcomeStatus] = mapped_column(
        Enum(OutcomeStatus, name="outcome_status"), default=OutcomeStatus.pending, index=True
    )
    outcome_date: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
