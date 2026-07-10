"""Import a finished Meet conference's transcript into call_transcripts.

This replaces the live bot/LiveKit/Deepgram capture for the post-meeting flow:
once a meeting ends (and was transcribed by Meet), pull the transcript via the
Meet REST API and persist it as CallTranscript rows. The existing
call_processor.process_call() then runs MOM + scoring + embeddings unchanged.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.google import meet
from app.models.call import Call
from app.models.transcript import CallTranscript

log = get_logger(__name__)

# Meet codes look like "abc-mnop-xyz".
_CODE_RE = re.compile(r"([a-z]{3}-[a-z]{4}-[a-z]{3})")


def meeting_code_from_url(url: str) -> str | None:
    m = _CODE_RE.search(url or "")
    return m.group(1) if m else None


def _parse_ts(value: str) -> dt.datetime:
    """Parse an RFC3339 timestamp (Meet uses a trailing 'Z')."""
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _speaker(entry: dict) -> str | None:
    # entry['participant'] is a resource name; keep just the trailing id for now.
    participant = entry.get("participant")
    return participant.split("/")[-1] if participant else None


async def import_transcript(
    db: AsyncSession, call_id: uuid.UUID, subject: str | None = None
) -> int:
    """Fetch the latest conference transcript for the call's meeting and store it.

    Returns the number of transcript entries imported (0 if the meeting hasn't
    ended yet or transcription was off). `subject` overrides the impersonated
    user (defaults to settings.google_impersonate_subject).
    """
    call = await db.get(Call, call_id)
    if call is None:
        raise ValueError(f"call {call_id} not found")
    code = meeting_code_from_url(call.meeting_url or "")
    if not code:
        raise ValueError(f"could not parse a Meet code from {call.meeting_url!r}")

    space = await meet.get_space(code, subject=subject)
    records = await meet.list_conference_records(space["name"], subject=subject)
    if not records:
        log.warning("no conference records for %s (meeting not ended/recorded?)", code)
        return 0

    # Most recent conference held in this space.
    record = sorted(records, key=lambda r: r.get("startTime", ""))[-1]
    conf_start = _parse_ts(record["startTime"])

    transcripts = await meet.list_transcripts(record["name"], subject=subject)
    if not transcripts:
        log.warning("conference %s has no transcript (transcription disabled?)", record["name"])
        return 0

    count = 0
    for t in transcripts:
        for e in await meet.list_transcript_entries(t["name"], subject=subject):
            start = _parse_ts(e["startTime"])
            end = _parse_ts(e["endTime"])
            db.add(
                CallTranscript(
                    call_id=call.id,
                    speaker_label=_speaker(e),
                    text=e.get("text", ""),
                    start_ts=(start - conf_start).total_seconds(),
                    end_ts=(end - conf_start).total_seconds(),
                    confidence=None,  # Meet doesn't expose per-entry confidence
                )
            )
            count += 1

    if call.started_at is None:
        call.started_at = conf_start
    if call.ended_at is None and record.get("endTime"):
        call.ended_at = _parse_ts(record["endTime"])

    await db.commit()
    log.info("imported %d transcript entries for call %s", count, call_id)
    return count
