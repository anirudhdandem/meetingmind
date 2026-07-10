"""MOM extraction schema + prompt (spec step 6, LLM call #1)."""

from pydantic import BaseModel, Field


class Attendee(BaseModel):
    name: str = Field(description="Attendee's real name; only use 'Unknown speaker N' if truly unidentifiable")
    role: str | None = Field(default=None, description="Title/role if mentioned")
    is_decision_maker: bool = False


class SpeakerName(BaseModel):
    """Maps one anonymous diarization label to the real person who spoke it."""

    label: str = Field(description="The diarization label exactly as it appears, e.g. '0' or '1'")
    name: str = Field(description="The real attendee name for this speaker (from the roster / context)")


class Contribution(BaseModel):
    name: str = Field(description="Attendee's real name (never 'Speaker 0')")
    summary: str = Field(description="What this person said, asked, or committed to, in 1-3 sentences")


class MomResult(BaseModel):
    """Structured minutes of meeting. Template: attendees, points discussed, action items,
    plus a per-person breakdown. Remaining fields are sales signals used for scoring."""

    # --- Speaker identification ---
    speaker_map: list[SpeakerName] = Field(
        default_factory=list,
        description="One entry for each diarization label STILL shown as 'Speaker N' in "
        "the transcript, mapping it to the real attendee name who spoke it. Speakers "
        "already shown by real name are confirmed — do NOT include them here. If a "
        "speaker cannot be confidently identified, map it to 'Speaker N' unchanged.",
    )

    # --- Core MOM template ---
    attendees: list[Attendee] = Field(default_factory=list)
    points_discussed: list[str] = Field(
        default_factory=list,
        description="Every important point/topic discussed, as concise bullets, in order",
    )
    action_items: list[str] = Field(
        default_factory=list,
        description="Concrete next steps to do AFTER the meeting; ALWAYS prefix with the owner's "
        "real name when known, e.g. 'Aneer: send the revised quote by Friday'",
    )
    contributions: list[Contribution] = Field(
        default_factory=list,
        description="One entry per attendee who spoke: their real name and a short summary of "
        "what they contributed. Use names, never 'Speaker 0/1'.",
    )

    # --- Sales signals (kept for scoring/comparison; optional) ---
    pain_points: list[str] = Field(default_factory=list, description="Customer problems/needs raised")
    objections: list[str] = Field(default_factory=list, description="Concerns/pushback raised")
    went_well: list[str] = Field(
        default_factory=list,
        description="What went well in this meeting — strong moments, good questions, "
        "moments that moved things forward. Concise bullets grounded in the transcript.",
    )
    to_improve: list[str] = Field(
        default_factory=list,
        description="What could have gone better — missed opportunities, unaddressed concerns, "
        "things to do differently next time. Concise, constructive bullets.",
    )
    next_steps: str = Field(default="", description="Agreed follow-up actions")
    decision_maker: str = Field(default="", description="Who owns the buying decision (real name), if identified")
    budget_signal: str = Field(default="", description="Any budget / timeline / authority signal")
    raw_summary: str = Field(
        description="2-4 sentence neutral summary of the call. Use the attendees' REAL NAMES "
        "throughout — never 'Speaker 0/1'."
    )


def build_mom_instructions(roster: list[str]) -> str:
    """MOM prompt, seeded with the real attendee roster read from the Meet call."""
    if roster:
        roster_line = (
            "These are the real attendees pulled from the meeting roster: "
            f"{', '.join(roster)}.\n"
            "Match each anonymous diarization speaker (Speaker 0/1/...) to one of these "
            "names. Some transcript lines may ALREADY show a real name instead of "
            "'Speaker N' — those speakers are confirmed; keep them exactly and do not "
            "rename them or add them to speaker_map."
        )
    else:
        roster_line = (
            "The attendee roster wasn't captured. Infer each speaker's name only from "
            "clear evidence in the conversation (self-introductions, sign-offs)."
        )

    return f"""\
You are a precise meeting analyst. From the transcript below, produce the minutes of \
meeting in this exact template:
  1. speaker_map — for each diarization label STILL shown as "Speaker 0/1/..." in the \
transcript, give the real name of the person who spoke it. {roster_line}
  2. attendees — everyone who took part, by real name.
  3. points_discussed — bullet every important topic/point raised, in the order discussed.
  4. action_items — every concrete next step to be done after the meeting; prefix each with \
the owner's real name (e.g. "Aneer: send pricing deck by Friday").
  5. contributions — for each attendee who spoke, summarise what THEY specifically said.
  6. went_well / to_improve — a short, candid retro: what went well in the meeting and what \
could have gone better. Ground every point in the transcript; be constructive, not generic.

Identifying speakers — read carefully, this is where mistakes happen:
- A name SPOKEN in a line usually identifies who is being ADDRESSED, not who is speaking. \
"Thank you, Dipti" or "Right, Arnika?" means the speaker is talking TO Dipti/Arnika — it is \
NOT evidence that the speaker IS Dipti/Arnika. Do not label a speaker with a name that only \
appears as someone they are addressing or thanking.
- Use the "HOW MUCH EACH SPEAKER TALKED" section: the speaker with the most talk time is \
usually a main participant, not someone who is merely mentioned once in passing.
- A person can be named in the roster yet barely speak (or not speak at all). Never assume the \
person whose name is mentioned is the one doing the talking.
- If you cannot identify a speaker with real confidence, DO NOT GUESS. Leave them as \
"Speaker N" (use that literal label as both the name and the speaker_map name). A correct \
"Speaker 1" is far better than a confident wrong name.

Rules:
- Use REAL NAMES everywhere you are confident; otherwise keep "Speaker N" consistently.
- Only use information present in the transcript — do not invent attendees, numbers, or commitments.
- Also fill the sales-signal fields when the call is a sales conversation; leave them empty otherwise.
- The transcript may be in Hindi or a Hindi/English mix — write the entire MOM in clear English.
"""
