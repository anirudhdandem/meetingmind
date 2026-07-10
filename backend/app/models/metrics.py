"""ORM model: call_metrics — team performance metrics for a call.

Two kinds of fields live here:
  * talk-time split (deterministic, from services.metrics.compute_talk_time)
  * confidence / answer-quality / conversion (LLM, from llm.performance)
One row per call, created alongside the MOM + score in call_processor.
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class CallMetrics(Base, UUIDPk, Timestamped):
    __tablename__ = "call_metrics"

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), index=True, unique=True
    )

    # --- Talk-time split (Phase 2, computed) ---
    team_talk_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    client_talk_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    unknown_talk_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    team_turns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_turns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Our share of the two-sided talk time (0-1); NULL when neither side was resolved.
    talk_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Team performance (Phase 3, LLM), all 0-100 ---
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_questions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    questions_answered: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Conversion probability (Phase 4, LLM), 0-100 ---
    conversion_probability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conversion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
