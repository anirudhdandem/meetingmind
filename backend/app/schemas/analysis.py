"""API schemas for MOM, scores, outcomes, and comparison."""

import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.outcome import OutcomeStatus


class MomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    call_id: uuid.UUID
    company_id: uuid.UUID
    attendees: list | None
    points_discussed: list | None
    action_items: list | None
    contributions: list | None
    pain_points: list | None
    objections: list | None
    went_well: list | None
    to_improve: list | None
    next_steps: str | None
    decision_maker: str | None
    budget_signal: str | None
    raw_summary: str | None
    created_at: datetime.datetime


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    call_id: uuid.UUID
    engagement_score: int | None
    objection_severity: int | None
    urgency_score: int | None
    technical_fit_score: int | None
    overall_rating: int | None
    qualitative_notes: str | None


class MetricsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    call_id: uuid.UUID
    # Talk-time split (Phase 2)
    team_talk_seconds: float | None
    client_talk_seconds: float | None
    unknown_talk_seconds: float | None
    team_turns: int | None
    client_turns: int | None
    talk_ratio: float | None
    # Team performance (Phase 3)
    confidence_score: int | None
    confidence_notes: str | None
    answer_quality_score: int | None
    answer_notes: str | None
    client_questions: int | None
    questions_answered: int | None
    # Conversion probability (Phase 4)
    conversion_probability: int | None
    conversion_notes: str | None


class OutcomeCreate(BaseModel):
    company_id: uuid.UUID
    call_id: uuid.UUID | None = None
    status: OutcomeStatus
    outcome_date: datetime.datetime | None = None
    outcome_notes: str | None = None


class OutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    call_id: uuid.UUID | None
    status: OutcomeStatus
    outcome_date: datetime.datetime | None
    outcome_notes: str | None


class SimilarCall(BaseModel):
    call_id: uuid.UUID | None
    company_id: uuid.UUID
    distance: float
    source_text: str | None


class RubricDelta(BaseModel):
    field: str
    won_avg: float
    lost_avg: float
    delta: float


class ComparisonReport(BaseModel):
    segment: str | None
    won_count: int
    lost_count: int
    deltas: list[RubricDelta]
    narrative: str
