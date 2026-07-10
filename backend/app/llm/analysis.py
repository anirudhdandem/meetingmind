"""Combined MOM + scoring in a single Gemini call ("one prompt, two sections")."""

from pydantic import BaseModel, Field

from app.llm import gemini_client
from app.llm.mom import MomResult, build_mom_instructions
from app.llm.performance import PerformanceResult, build_performance_instructions
from app.llm.scoring import SCORING_RUBRIC, ScoreResult
from app.llm.sides import SidesResult, build_sides_instructions


class CallAnalysis(BaseModel):
    """The four output sections produced from one transcript pass."""

    mom: MomResult
    # Default-empty: if the model ever omits `sides`, role attribution degrades to
    # the deterministic sources instead of failing the whole analysis.
    sides: SidesResult = Field(default_factory=SidesResult)
    scores: ScoreResult
    performance: PerformanceResult


def _format_stats(stats) -> str:
    """Render per-speaker talk-time so the model can reason about who talked most."""
    if not stats:
        return ""
    lines = []
    for s in stats:
        who = f"Speaker {s.label}" if str(s.label).isdigit() else str(s.label)
        lines.append(f"- {who}: {s.seconds:.0f}s across {s.turns} turns")
    return "=== HOW MUCH EACH SPEAKER TALKED ===\n" + "\n".join(lines) + "\n\n"


def build_prompt(
    transcript: str,
    roster: list[str],
    stats=None,
    sides=None,
    our_company: str | None = None,
    client_company: str | None = None,
) -> str:
    roster_block = ", ".join(roster) if roster else "(roster not captured)"
    return (
        f"{build_mom_instructions(roster)}\n"
        f"{build_sides_instructions(sides, our_company, client_company)}\n"
        f"{SCORING_RUBRIC}\n"
        f"{build_performance_instructions(sides)}\n"
        "Return JSON with four top-level keys: `mom`, `sides`, `scores`, and "
        "`performance`, each matching its schema.\n\n"
        f"=== ATTENDEE ROSTER (real names) ===\n{roster_block}\n\n"
        f"{_format_stats(stats)}"
        f"=== TRANSCRIPT ===\n{transcript}\n=== END TRANSCRIPT ==="
    )


async def analyze(
    transcript: str,
    roster: list[str] | None = None,
    stats=None,
    sides=None,
    our_company: str | None = None,
    client_company: str | None = None,
) -> CallAnalysis:
    """Run MOM + side classification + rubric scoring + team-performance in one call.

    `roster` is the real attendee names read from the Meet call; the model uses them to
    label speakers and write the MOM with names instead of diarization indices. `stats`
    is per-speaker talk time (from speaker_attribution.speaking_time_stats) so the model
    can align "who spoke most" with the roster instead of guessing from spoken names.
    `sides` is {"internal": [...names], "client": [...names]} — whatever the
    deterministic sources (calendar emails, team roster) already confirmed; the model's
    `sides` section classifies every remaining named speaker from transcript evidence,
    and the performance section grades the internal side. `our_company`/`client_company`
    anchor the classification ("who sells" vs "who buys"). Speakers already shown by
    real name in the transcript are ground-truth resolved and must not be renamed.
    """
    return await gemini_client.generate_structured(
        build_prompt(transcript, roster or [], stats, sides, our_company, client_company),
        CallAnalysis,
    )
