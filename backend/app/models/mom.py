"""ORM model: moms — LLM-extracted minutes of meeting (spec step 6)."""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class Mom(Base, UUIDPk, Timestamped):
    __tablename__ = "moms"

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    attendees: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Core MOM template: the important points raised and the agreed follow-up tasks.
    points_discussed: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    action_items: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Per-attendee breakdown: [{name, summary}] — who said what, by real name.
    contributions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    pain_points: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    objections: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Post-meeting coaching: what went well and what could have gone better.
    went_well: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    to_improve: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_maker: Mapped[str | None] = mapped_column(String, nullable=True)
    budget_signal: Mapped[str | None] = mapped_column(String, nullable=True)
    # raw_summary is the text embedded into company_memory (spec step 7).
    raw_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
