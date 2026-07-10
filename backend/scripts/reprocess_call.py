"""Re-run the MOM pipeline for an existing call (clears the old MOM first).

Use after fixing speaker attribution to regenerate a call's transcript labels, MOM,
scores, and company memory from its recording. For a call recorded before the
active-speaker timeline existed, pass --map to supply ground-truth names by
diarization index (run once without --map first to see each label's talk time).

Usage:
    # inspect: print each diarization label's talk time + a sample line
    python -m scripts.reprocess_call <call_id> --show

    # re-run using the hardened LLM naming (no manual override)
    python -m scripts.reprocess_call <call_id>

    # re-run forcing ground-truth names (index=Name, comma-separated)
    python -m scripts.reprocess_call <call_id> --map "0=Artha Vault,1=Animesh Kumar"
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models.embedding import CompanyMemory
from app.models.mom import Mom
from app.models.score import CallScore
from app.models.transcript import CallTranscript
from app.services import speaker_attribution
from app.services.call_processor import (
    _rebuild_transcript_from_recording,
    process_call,
)


def _parse_map(raw: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in (raw or "").split(","):
        pair = pair.strip()
        if not pair:
            continue
        k, _, v = pair.partition("=")
        if k.strip() and v.strip():
            out[k.strip()] = v.strip()
    return out


async def _show(call_id: uuid.UUID) -> None:
    """Rebuild the transcript and print per-label talk time so --map can be chosen."""
    async with SessionLocal() as db:
        await _rebuild_transcript_from_recording(db, call_id)
        await db.commit()
        chunks = (
            await db.execute(
                select(CallTranscript)
                .where(CallTranscript.call_id == call_id)
                .order_by(CallTranscript.start_ts)
            )
        ).scalars().all()
    stats = speaker_attribution.speaking_time_stats(chunks)
    print(f"\n{len(chunks)} utterances across {len(stats)} diarization labels:\n")
    for s in stats:
        print(f"  Speaker {s.label}: {s.seconds:.0f}s / {s.turns} turns")
        print(f"    e.g. {s.sample_text!r}\n")


async def _clear(call_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(Mom).where(Mom.call_id == call_id))
        await db.execute(delete(CallScore).where(CallScore.call_id == call_id))
        await db.execute(delete(CompanyMemory).where(CompanyMemory.call_id == call_id))
        await db.commit()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("call_id")
    ap.add_argument("--map", dest="map", default=None, help='e.g. "0=Artha Vault,1=Animesh Kumar"')
    ap.add_argument("--show", action="store_true", help="only print per-label talk time")
    args = ap.parse_args()

    call_id = uuid.UUID(args.call_id)
    if args.show:
        await _show(call_id)
        return

    manual = _parse_map(args.map)
    await _clear(call_id)
    async with SessionLocal() as db:
        mom = await process_call(db, call_id, manual_labels=manual or None)
    if mom is None:
        print("No MOM produced (empty transcript?)")
        return
    print("\n=== NEW MOM ===")
    print(mom.raw_summary, "\n")
    for c in mom.contributions or []:
        print(f"- {c.get('name')}: {c.get('summary')}")


if __name__ == "__main__":
    asyncio.run(main())
