"""LiveKit Agent: subscribe to the bot's audio track, run Deepgram STT, write live chunks.

Run as a LiveKit Agents worker:
    python -m app.agent.transcription_agent dev      # or: start

The worker is dispatched into a room, resolves which `call` the room belongs to (by
`livekit_room` name), and writes every FINAL Deepgram segment to `call_transcripts`
immediately — giving the crash-safe, live chunk storage from spec step 3.

API NOTE: targets livekit-agents ~1.x + livekit-plugins-deepgram. Pin versions in
requirements if the SpeechEvent / STT surface differs in your installed build.
"""

from __future__ import annotations

import asyncio
import uuid

from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.agents.stt import SpeechEventType
from livekit.plugins import deepgram
from sqlalchemy import select

from app.bot.livekit_publisher import BOT_IDENTITY
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.config import get_settings
from app.models.call import Call
from app.models.transcript import CallTranscript

log = get_logger(__name__)


async def _resolve_call_id(room_name: str) -> uuid.UUID | None:
    async with SessionLocal() as db:
        call = (await db.execute(select(Call).where(Call.livekit_room == room_name))).scalars().first()
        return call.id if call else None


async def _write_chunk(call_id: uuid.UUID, alt) -> None:
    text = (alt.text or "").strip()
    if not text:
        return
    async with SessionLocal() as db:
        db.add(
            CallTranscript(
                call_id=call_id,
                speaker_label=str(alt.speaker_id) if getattr(alt, "speaker_id", None) is not None else None,
                text=text,
                start_ts=float(getattr(alt, "start_time", 0.0) or 0.0),
                end_ts=float(getattr(alt, "end_time", 0.0) or 0.0),
                confidence=getattr(alt, "confidence", None),
            )
        )
        await db.commit()
    log.info("chunk [%s] %s", call_id, text[:80])


async def _transcribe_track(track: rtc.Track, call_id: uuid.UUID) -> None:
    s = get_settings()
    stt = deepgram.STT(
        api_key=s.deepgram_api_key,
        model=s.deepgram_model,
        language=s.deepgram_language,  # "multi" = Hindi/English code-switching (nova-3)
        enable_diarization=True,  # plugin renamed this from `diarize`
        punctuate=True,
        smart_format=True,
        interim_results=True,
    )
    audio_stream = rtc.AudioStream(track)
    stt_stream = stt.stream()

    async def _pump() -> None:
        async for ev in audio_stream:
            stt_stream.push_frame(ev.frame)
        stt_stream.end_input()

    pump = asyncio.create_task(_pump())
    try:
        async for ev in stt_stream:
            if ev.type == SpeechEventType.FINAL_TRANSCRIPT and ev.alternatives:
                await _write_chunk(call_id, ev.alternatives[0])
    finally:
        pump.cancel()
        await stt_stream.aclose()


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    call_id = await _resolve_call_id(ctx.room.name)
    if call_id is None:
        log.warning("No call mapped to room %s; transcripts will be dropped", ctx.room.name)
        return
    log.info("Transcription agent attached to room %s (call %s)", ctx.room.name, call_id)

    started: set[str] = set()

    def _maybe_start(track: rtc.Track | None, participant: rtc.RemoteParticipant) -> None:
        if (
            track is not None
            and track.kind == rtc.TrackKind.KIND_AUDIO
            and participant.identity == BOT_IDENTITY
            and participant.identity not in started
        ):
            started.add(participant.identity)
            log.info("Subscribed to bot audio; starting STT")
            asyncio.create_task(_transcribe_track(track, call_id))

    @ctx.room.on("track_subscribed")
    def _on_track(track: rtc.Track, pub, participant: rtc.RemoteParticipant) -> None:
        _maybe_start(track, participant)

    # Race fix: the bot's track is often already subscribed during connect()
    # (it was published before we joined), so the event above never fires for
    # it. Sweep already-present tracks once on startup.
    for p in ctx.room.remote_participants.values():
        for pub in p.track_publications.values():
            if pub.subscribed:
                _maybe_start(pub.track, p)


if __name__ == "__main__":
    import os

    # The livekit-agents CLI reads these straight from the OS environment (it
    # doesn't use our pydantic .env loader), so seed them from our settings.
    s = get_settings()
    os.environ.setdefault("LIVEKIT_URL", s.livekit_url)
    os.environ.setdefault("LIVEKIT_API_KEY", s.livekit_api_key)
    os.environ.setdefault("LIVEKIT_API_SECRET", s.livekit_api_secret)

    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
