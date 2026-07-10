"""Post-meeting batch transcription via Deepgram's pre-recorded API.

Streaming STT is lossy by nature — it runs in real time and drops audio to
endpointing, reconnects and network hiccups. To guarantee that EVERY word makes
it into the MOM, the bot keeps a full-fidelity WAV of the whole meeting; once the
call ends we transcribe that complete file in a single batch pass. The result —
diarized utterances with timestamps — is the authoritative transcript the MOM is
built from. The live streaming agent is only a best-effort preview.

Docs: https://developers.google.com/ (Deepgram) /docs/pre-recorded-audio
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

DEEPGRAM_PRERECORDED_URL = "https://api.deepgram.com/v1/listen"

# Long meetings produce large files and take a while server-side; give it room.
_HTTP_TIMEOUT = httpx.Timeout(connect=30.0, read=900.0, write=900.0, pool=30.0)


@dataclass
class Utterance:
    """One diarized speaker turn — maps 1:1 onto a CallTranscript row."""

    speaker_label: str | None
    text: str
    start_ts: float
    end_ts: float
    confidence: float | None


async def _file_chunks(path: Path, chunk_size: int = 1 << 20) -> AsyncIterator[bytes]:
    """Stream the WAV off disk so a multi-hundred-MB meeting isn't held in memory.

    Must be an *async* generator: httpx's AsyncClient rejects a sync byte stream for
    a request body (RuntimeError: sync request with an AsyncClient). Disk reads run
    in a thread so they don't block the event loop.
    """
    with path.open("rb") as f:
        while True:
            block = await asyncio.to_thread(f.read, chunk_size)
            if not block:
                break
            yield block


def _parse(data: dict) -> list[Utterance]:
    """Pull the diarized utterances out of a Deepgram pre-recorded response."""
    utterances = (data.get("results") or {}).get("utterances") or []
    out: list[Utterance] = []
    for u in utterances:
        text = (u.get("transcript") or "").strip()
        if not text:
            continue
        speaker = u.get("speaker")
        out.append(
            Utterance(
                speaker_label=str(speaker) if speaker is not None else None,
                text=text,
                start_ts=float(u.get("start") or 0.0),
                end_ts=float(u.get("end") or 0.0),
                confidence=u.get("confidence"),
            )
        )
    return out


async def transcribe_file(path: Path) -> list[Utterance]:
    """Transcribe a complete WAV recording into ordered, diarized utterances.

    Raises on transport/API errors so the caller can fall back to live chunks.
    """
    s = get_settings()
    params = {
        "model": s.deepgram_model,
        "language": s.deepgram_language,  # "multi" = Hindi/English code-switching (nova-3)
        "diarize": "true",
        "punctuate": "true",
        "smart_format": "true",
        "utterances": "true",  # segment the result into speaker turns
    }
    headers = {
        "Authorization": f"Token {s.deepgram_api_key}",
        "Content-Type": "audio/wav",
    }
    log.info("Batch-transcribing recording %s", path)
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(
            DEEPGRAM_PRERECORDED_URL,
            params=params,
            headers=headers,
            content=_file_chunks(path),
        )
        resp.raise_for_status()
        data = resp.json()
    utterances = _parse(data)
    log.info("Batch transcript for %s: %d utterances", path, len(utterances))
    return utterances
