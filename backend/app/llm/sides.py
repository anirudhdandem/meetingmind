"""Speaker side inference for the ANALYSIS PROMPT ONLY — never for role decisions.

Roles that feed the metrics are decided exclusively by deterministic evidence (Meet
participant identity via the bot's account, calendar emails, the team roster — see
services/participant_roles.py). This section exists so the model states who it
believes sits on which side BEFORE grading "our team's" performance: when the
deterministic sides are incomplete (e.g. an anonymous joiner), the performance
section grades the side classified here instead of guessing implicitly. Nothing in
this output is persisted or stamped onto transcript segments.
"""

from pydantic import BaseModel, Field

INTERNAL = "internal"
CLIENT = "client"

HIGH = "high"
MEDIUM = "medium"
LOW = "low"


class SpeakerSide(BaseModel):
    """One named speaker's side of the table, with the evidence for it."""

    name: str = Field(
        description="The speaker's name exactly as it appears in the transcript/roster"
    )
    side: str = Field(
        description="'internal' (our team — the sellers) or 'client' (the buyers/prospects)"
    )
    confidence: str = Field(
        description="'high' (explicit evidence: self-introduction, states their company, "
        "clearly runs the demo/pitch), 'medium' (strong behavioral evidence), or "
        "'low' (a guess — ambiguous either way)"
    )
    evidence: str = Field(
        description="One short quote or concrete observation from the transcript that "
        "justifies the side, e.g. \"says 'let me share our pricing tiers'\""
    )


class SidesResult(BaseModel):
    """Side classification for every named speaker on the call."""

    speakers: list[SpeakerSide] = Field(
        default_factory=list,
        description="One entry per NAMED attendee/speaker (skip unresolved 'Speaker N' "
        "labels). Include the pre-confirmed names too, echoed with confidence 'high'.",
    )


def build_sides_instructions(
    known_sides: dict[str, list[str]] | None,
    our_company: str | None,
    client_company: str | None,
) -> str:
    """Side-classification prompt, seeded with whatever we already know for certain."""
    known_sides = known_sides or {}
    known_internal = ", ".join(known_sides.get(INTERNAL) or []) or "(none confirmed yet)"
    known_client = ", ".join(known_sides.get(CLIENT) or []) or "(none confirmed yet)"
    us = our_company or "our company"
    them = f"'{client_company}'" if client_company else "the prospect company"

    return f"""\
=== SIDE CLASSIFICATION (who is on which side of the table) ===
This is a call between {us} (OUR team, the sellers) and {them} (the CLIENT/buyers).
Produce a `sides` section classifying EVERY named attendee as 'internal' or 'client'.

Already confirmed — echo these unchanged with confidence 'high':
- Confirmed internal ({us}): {known_internal}
- Confirmed client: {known_client}

For everyone else, decide from transcript evidence:
- INTERNAL signals: presents/demos the product, answers product or pricing questions,
  says "our product/platform/team", proposes next steps or follow-ups, introduces the
  agenda, self-identifies with {us}.
- CLIENT signals: evaluates, asks about features/pricing/security, describes THEIR OWN
  company's needs/workflows/pain points, self-identifies with {them}, decides whether
  to buy.
- Self-introductions ("I'm Priya from {client_company or 'Acme'}") are the strongest
  evidence — use them whenever present.
- People on the same side talk to their colleagues differently than to the other side
  (handing off: "X, do you want to take that one?" usually means X is a colleague).

Confidence: 'high' only with explicit evidence (introduction, company statement, or
they clearly ran the pitch/demo); 'medium' for strong behavioral evidence; 'low' if
genuinely ambiguous. Never invent names — classify only speakers who actually appear.
Give one short piece of evidence per person.
"""
