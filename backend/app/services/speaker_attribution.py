"""Ground-truth speaker attribution from a Meet active-speaker timeline.

The bot records ONE mixed mono stream, so Deepgram diarization can only tell voices
apart as anonymous clusters ("0", "1", ...). Turning those clusters into real names
used to be a pure LLM guess from conversational cues — which is exactly how a client
who was merely *thanked* by name ("Thank you, Dipti") ended up owning every line the
actual main speaker said.

This module removes the guessing when we have ground truth: during the call the bot
samples Meet's own "who is speaking right now" signal (see app.bot.speaker_tracker)
into a timeline. Here we correlate that timeline against the diarized transcript by
time overlap and assign each diarization label the real name that was speaking during
most of that label's turns. Cluster-level majority voting makes this robust to small
timing skew and the odd bad sample.

Timeline sidecar format (JSON, one file per call next to the WAV):
    {"version": 1, "poll_interval": 0.5,
     "samples": [{"t": 12.3, "speakers": ["Artha Vault"]}, ...]}
`t` is seconds from the START of the WAV recording (same clock Deepgram timestamps
are relative to), so a sample and a transcript utterance are directly comparable.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# A diarization label is only bound to a name when the timeline actually covers its
# turns AND one name clearly dominates — otherwise we leave it for the LLM fallback
# rather than assert a shaky ground truth.
_MIN_SAMPLES_PER_LABEL = 3       # need at least this many overlapping speaker samples
_MIN_WINNER_SHARE = 0.55         # winning name must hold >= this share of the overlap


@dataclass
class SpeakerSample:
    """One 'who is speaking now' reading, `t` seconds after recording start."""

    t: float
    speakers: list[str]


def timeline_path(call_id: uuid.UUID) -> Path:
    """Sidecar next to the call's WAV holding the active-speaker timeline."""
    return Path(get_settings().recordings_dir) / f"{call_id}.speakers.json"


def write_timeline(path: Path, samples: list[SpeakerSample], poll_interval: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "poll_interval": poll_interval,
        "samples": [{"t": round(s.t, 3), "speakers": s.speakers} for s in samples],
    }
    path.write_text(json.dumps(payload))
    log.info("Wrote active-speaker timeline (%d samples) -> %s", len(samples), path)


def load_timeline(call_id: uuid.UUID) -> tuple[list[SpeakerSample], float]:
    """Load a call's active-speaker timeline. Returns ([], default) when absent."""
    path = timeline_path(call_id)
    if not path.exists():
        return [], 0.5
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        log.warning("Could not read speaker timeline %s", path, exc_info=True)
        return [], 0.5
    samples = [
        SpeakerSample(t=float(s.get("t", 0.0)), speakers=list(s.get("speakers") or []))
        for s in data.get("samples") or []
    ]
    return samples, float(data.get("poll_interval") or 0.5)


def _norm(name: str) -> str:
    """Loose key for matching names across sources (roster vs Meet tile vs caption)."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _match_roster(name: str, roster: list[str]) -> str:
    """Prefer the roster's spelling/casing for a timeline name; else return it as-is."""
    key = _norm(name)
    for r in roster:
        rk = _norm(r)
        if rk and (rk == key or rk in key or key in rk):
            return r
    return name


# Public so call_processor can surface it in logs and hand it to the LLM fallback.
@dataclass
class LabelStat:
    label: str
    seconds: float
    turns: int
    sample_text: str


def speaking_time_stats(chunks) -> list[LabelStat]:
    """Per diarization label: how much it spoke, ordered loudest first.

    Giving this to the LLM fallback is what lets it reason about *who actually talked
    most* instead of latching onto whichever name happened to be said aloud.
    """
    by_label: dict[str, list] = defaultdict(list)
    for c in chunks:
        if c.speaker_label is not None:
            by_label[str(c.speaker_label)].append(c)
    stats: list[LabelStat] = []
    for label, cs in by_label.items():
        secs = sum(max(0.0, c.end_ts - c.start_ts) for c in cs)
        longest = max(cs, key=lambda c: c.end_ts - c.start_ts)
        stats.append(
            LabelStat(
                label=label,
                seconds=round(secs, 1),
                turns=len(cs),
                sample_text=(longest.text or "")[:120],
            )
        )
    stats.sort(key=lambda s: s.seconds, reverse=True)
    return stats


def correlate_labels_to_names(
    chunks, samples: list[SpeakerSample], roster: list[str], poll_interval: float
) -> dict[str, str]:
    """Map diarization labels -> real names using the active-speaker timeline.

    For every transcript turn we collect the speaker samples that fall inside it and
    tally, per diarization label, how long each real name was the one speaking. Each
    label is then assigned the name that dominated its turns — but only when the
    timeline covered enough of them and one name clearly won. Labels that don't clear
    the bar are left out (the caller falls back to the LLM for those).
    """
    if not samples or not chunks:
        return {}

    samples = sorted(samples, key=lambda s: s.t)
    # overlap[label][name] = accumulated seconds that `name` was speaking during `label`'s turns
    overlap: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: dict[str, int] = defaultdict(int)  # number of contributing samples per label

    si = 0
    n = len(samples)
    for c in sorted(chunks, key=lambda c: c.start_ts):
        if c.speaker_label is None:
            continue
        label = str(c.speaker_label)
        # advance the sample cursor to the first sample not before this turn
        while si < n and samples[si].t < c.start_ts:
            si += 1
        j = si
        while j < n and samples[j].t <= c.end_ts:
            spk = samples[j].speakers
            if spk:
                # a sample "covers" ~poll_interval of time; split it across concurrent speakers
                w = poll_interval / len(spk)
                for name in spk:
                    overlap[label][name] += w
                counts[label] += 1
            j += 1

    mapping: dict[str, str] = {}
    for label, names in overlap.items():
        if counts[label] < _MIN_SAMPLES_PER_LABEL:
            continue
        total = sum(names.values())
        if total <= 0:
            continue
        winner, wsecs = max(names.items(), key=lambda kv: kv[1])
        share = wsecs / total
        if share < _MIN_WINNER_SHARE:
            log.info(
                "Timeline for label %s inconclusive (winner %s only %.0f%%) — leaving to LLM",
                label, winner, share * 100,
            )
            continue
        mapping[label] = _match_roster(winner, roster)

    if mapping:
        log.info("Ground-truth speaker map from timeline: %s", mapping)
    return mapping
