"""Comparative analysis (spec step 10, LLM call #3).

Critically: rubric deltas are computed in Python *first* (see services/comparison_service),
and the LLM is only asked to explain numbers it is given — never to invent the comparison.
This grounds the narrative and avoids hallucinated causal stories.
"""

from pydantic import BaseModel, Field


class ComparisonNarrative(BaseModel):
    narrative: str = Field(
        description="Grounded explanation of why the 'won' cohort outperformed the 'lost' cohort, "
        "referencing the provided rubric deltas and summaries only."
    )


def build_prompt(segment: str | None, deltas_text: str, won_summaries: str, lost_summaries: str) -> str:
    seg = segment or "all segments"
    return f"""\
You are a sales strategy analyst. For the segment "{seg}", you are given pre-computed average
rubric deltas between WON and LOST deals, plus representative call summaries from each cohort.

Explain what distinguishes won from lost deals. Ground every claim in the deltas and summaries
below — do NOT introduce factors that are not supported by this data, and do NOT recompute or
dispute the numbers; treat them as authoritative.

=== RUBRIC DELTAS (won_avg - lost_avg) ===
{deltas_text}

=== REPRESENTATIVE WON SUMMARIES ===
{won_summaries}

=== REPRESENTATIVE LOST SUMMARIES ===
{lost_summaries}
"""
