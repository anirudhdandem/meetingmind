"""Team-performance analysis: pitch confidence, answer quality, conversion odds.

Third section of the single Gemini analysis call (alongside MOM + scoring). Unlike
the rubric (which scores the *deal*), this judges *our team's* showing, so it needs
to know which speakers are ours vs the client — passed in as `sides`.
"""

from pydantic import BaseModel, Field


class PerformanceResult(BaseModel):
    """How our team performed on the call. All scores 0-100."""

    confidence_score: int = Field(
        ge=0, le=100,
        description="How confident/assured OUR team sounded delivering the pitch — tone, "
        "assertiveness, command of the material, few fillers/hedges. 0=hesitant, 100=commanding.",
    )
    confidence_notes: str = Field(
        description="1-2 sentences justifying the confidence score, grounded in the transcript."
    )
    answer_quality_score: int = Field(
        ge=0, le=100,
        description="How well OUR team answered the client's questions/objections — "
        "responsiveness, completeness, and apparent accuracy. 0=dodged or wrong, 100=fully addressed.",
    )
    answer_notes: str = Field(
        description="1-2 sentences on how well our team handled the client's questions/objections."
    )
    client_questions: int = Field(
        ge=0, description="Number of distinct questions or objections the CLIENT raised."
    )
    questions_answered: int = Field(
        ge=0,
        description="How many of those client questions/objections our team actually addressed "
        "with a real answer (<= client_questions).",
    )
    conversion_probability: int = Field(
        ge=0, le=100,
        description="Estimated probability (0-100) this company converts into a paying customer, "
        "from buying signals, engagement, urgency, and how serious the objections were.",
    )
    conversion_notes: str = Field(
        description="1-2 sentences justifying the conversion estimate, grounded in the transcript."
    )


def build_performance_instructions(sides: dict[str, list[str]] | None) -> str:
    """Performance prompt, seeded with which attendees are our team vs the client."""
    sides = sides or {}
    internal = ", ".join(sides.get("internal") or []) or "(not identified)"
    client = ", ".join(sides.get("client") or []) or "(not identified)"
    return f"""\
=== SIDES (who is who) ===
Our team (the SELLERS, whose performance you are grading): {internal}
Client / prospect (the BUYERS): {client}
If a side is "(not identified)" or incomplete, use YOUR OWN `sides` classification: \
grade the speakers you classified as 'internal' there, never the ones you classified \
as 'client'.

Produce a `performance` section grading OUR TEAM's showing (never the client's):
- confidence_score + confidence_notes: how assured and in-command our team sounded.
- answer_quality_score + answer_notes: how well our team answered the client's questions \
and objections (responsiveness, completeness, accuracy).
- client_questions: count the distinct questions/objections the CLIENT raised.
- questions_answered: how many of those our team actually addressed with a real answer.
- conversion_probability + conversion_notes: your best estimate this deal converts.
Base every judgement strictly on transcript evidence. Do not reward confident-sounding \
but evasive answers — a clear "I'll find out" beats a confident non-answer.
"""
