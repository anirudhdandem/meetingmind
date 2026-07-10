"""Won-vs-lost comparison: compute rubric deltas in Python, then ask Gemini to explain them."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm import comparison as comparison_llm
from app.llm import gemini_client
from app.models.call import Call
from app.models.company import Company
from app.models.mom import Mom
from app.models.outcome import LeadOutcome, OutcomeStatus
from app.models.score import CallScore
from app.schemas.analysis import ComparisonReport, RubricDelta

log = get_logger(__name__)

_RUBRIC_FIELDS = [
    "engagement_score",
    "objection_severity",
    "urgency_score",
    "technical_fit_score",
    "overall_rating",
]


async def _cohort(session: AsyncSession, segment: str | None, status: OutcomeStatus):
    """Return (scores, summaries) for calls in a segment with a given outcome status."""
    stmt = (
        select(CallScore, Mom.raw_summary)
        .join(LeadOutcome, LeadOutcome.call_id == CallScore.call_id)
        .join(Call, Call.id == CallScore.call_id)
        .join(Company, Company.id == Call.company_id)
        .join(Mom, Mom.call_id == CallScore.call_id, isouter=True)
        .where(LeadOutcome.status == status)
    )
    if segment is not None:
        stmt = stmt.where(Company.segment == segment)

    rows = (await session.execute(stmt)).all()
    scores = [r[0] for r in rows]
    summaries = [r[1] for r in rows if r[1]]
    return scores, summaries


def _avg(scores, field: str) -> float:
    vals = [getattr(s, field) for s in scores if getattr(s, field) is not None]
    return round(sum(vals) / len(vals), 1) if vals else 0.0


async def compare(session: AsyncSession, segment: str | None) -> ComparisonReport:
    won_scores, won_summaries = await _cohort(session, segment, OutcomeStatus.accepted)
    lost_scores, lost_summaries = await _cohort(session, segment, OutcomeStatus.rejected)

    deltas = [
        RubricDelta(
            field=f,
            won_avg=_avg(won_scores, f),
            lost_avg=_avg(lost_scores, f),
            delta=round(_avg(won_scores, f) - _avg(lost_scores, f), 1),
        )
        for f in _RUBRIC_FIELDS
    ]

    if not won_scores or not lost_scores:
        narrative = (
            "Not enough labelled outcomes to compare "
            f"(won={len(won_scores)}, lost={len(lost_scores)}). "
            "Label more deals via /outcomes to enable comparison."
        )
        return ComparisonReport(
            segment=segment,
            won_count=len(won_scores),
            lost_count=len(lost_scores),
            deltas=deltas,
            narrative=narrative,
        )

    deltas_text = "\n".join(f"- {d.field}: won {d.won_avg} vs lost {d.lost_avg} (Δ {d.delta:+})" for d in deltas)
    prompt = comparison_llm.build_prompt(
        segment=segment,
        deltas_text=deltas_text,
        won_summaries="\n".join(f"- {s}" for s in won_summaries[:8]) or "(none)",
        lost_summaries="\n".join(f"- {s}" for s in lost_summaries[:8]) or "(none)",
    )
    result = await gemini_client.generate_structured(prompt, comparison_llm.ComparisonNarrative)

    return ComparisonReport(
        segment=segment,
        won_count=len(won_scores),
        lost_count=len(lost_scores),
        deltas=deltas,
        narrative=result.narrative,
    )
