"""Deterministic per-call metrics computed straight from the transcript.

Phase 2: talk-time split by side. Each transcript segment carries a `role`
(internal/client/unknown, set by participant_roles); we sum durations and turns per
side. Purely arithmetic — no LLM — so it's the most reliable metric we produce, only
as good as the role attribution feeding it.
"""

from __future__ import annotations


def compute_talk_time(chunks) -> dict:
    """Seconds and turns spoken per side, plus our share of the (known) talk time.

    talk_ratio is internal / (internal + client), i.e. how much of the two-sided
    conversation was us — None when neither side is known (roles never resolved).
    """
    seconds = {"internal": 0.0, "client": 0.0, "unknown": 0.0}
    turns = {"internal": 0, "client": 0, "unknown": 0}
    for c in chunks:
        role = c.role if c.role in seconds else "unknown"
        seconds[role] += max(0.0, (c.end_ts or 0.0) - (c.start_ts or 0.0))
        turns[role] += 1

    known = seconds["internal"] + seconds["client"]
    talk_ratio = (seconds["internal"] / known) if known > 0 else None
    return {
        "team_talk_seconds": round(seconds["internal"], 1),
        "client_talk_seconds": round(seconds["client"], 1),
        "unknown_talk_seconds": round(seconds["unknown"], 1),
        "team_turns": turns["internal"],
        "client_turns": turns["client"],
        "talk_ratio": round(talk_ratio, 3) if talk_ratio is not None else None,
    }
