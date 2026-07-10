"""Rubric scoring schema + prompt (spec step 8, LLM call #2)."""

from pydantic import BaseModel, Field


class ScoreResult(BaseModel):
    """Rubric scores for a sales call. All numeric fields are 0-100."""

    engagement_score: int = Field(ge=0, le=100, description="Prospect attentiveness/participation")
    objection_severity: int = Field(ge=0, le=100, description="How serious the objections were (higher = worse)")
    urgency_score: int = Field(ge=0, le=100, description="Buying urgency / timeline pressure")
    technical_fit_score: int = Field(ge=0, le=100, description="Fit between product and stated needs")
    overall_rating: int = Field(ge=0, le=100, description="Holistic likelihood-to-progress score")
    qualitative_notes: str = Field(description="2-3 sentences justifying the scores, grounded in the transcript")


SCORING_RUBRIC = """\
Score the call against this rubric (each 0-100):
- engagement_score: prospect attentiveness, question-asking, participation. Low = one-sided.
- objection_severity: seriousness of concerns raised (HIGHER means MORE/worse objections).
- urgency_score: explicit timeline pressure, compelling event, deadline.
- technical_fit_score: how well the product maps to the stated pain points.
- overall_rating: holistic likelihood this deal progresses.
Base every score strictly on transcript evidence; explain briefly in qualitative_notes.
"""
