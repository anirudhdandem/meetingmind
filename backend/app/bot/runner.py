"""Orchestrate a single call: set up audio routing, join Meet, pump audio into LiveKit."""

from __future__ import annotations

import asyncio
import datetime
import uuid
import wave

from app.bot import profiles
from app.bot.audio_capture import CHANNELS, SAMPLE_RATE, PulseAudioCapture
from app.bot.livekit_publisher import LiveKitPublisher
from app.bot.meet_bot import MeetBot
from app.bot.speaker_tracker import RecordingClock, track_active_speakers
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models.call import Call, CallStatus
from app.services import speaker_attribution
from app.services.call_processor import process_call, recording_path
from app.services.speaker_attribution import SpeakerSample

log = get_logger(__name__)


async def _set_status(call_id: uuid.UUID, status: CallStatus, *, started: bool = False, ended: bool = False):
    async with SessionLocal() as db:
        call = await db.get(Call, call_id)
        if call is None:
            return
        call.status = status
        now = datetime.datetime.now(datetime.timezone.utc)
        if started:
            call.started_at = now
        if ended:
            call.ended_at = now
        await db.commit()


async def run_bot_for_call(
    call_id: uuid.UUID, stop_event: asyncio.Event | None = None
) -> None:
    """Join the meeting for `call_id` and stream its audio into the call's LiveKit room.

    If `stop_event` is provided, setting it makes the bot leave immediately (this is
    how the frontend "End meeting" button cuts the call). Either way, once the session
    ends the call-end pipeline runs and produces the MOM.
    """
    async with SessionLocal() as db:
        call = await db.get(Call, call_id)
        if call is None:
            raise ValueError(f"call {call_id} not found")
        if not call.meeting_url or not call.livekit_room:
            raise ValueError("call is missing meeting_url or livekit_room")
        meeting_url, room = call.meeting_url, call.livekit_room

    capture = PulseAudioCapture()
    publisher = LiveKitPublisher(room)
    slot: profiles.ProfileSlot | None = None
    bot: MeetBot | None = None

    try:
        # Each concurrent bot needs its own Chromium profile (the dir is locked by
        # the browser), so reserve a slot from the pool — seeded from the master
        # signed-in profile, so no extra Google account or re-login is needed.
        slot = await asyncio.to_thread(profiles.acquire)
        bot = MeetBot(meeting_url, user_data_dir=str(slot.path))

        # Order matters: create+default the sink BEFORE the browser starts so Meet's
        # audio is routed into it.
        await capture.setup()
        await publisher.connect()
        await bot.join()
        await _set_status(call_id, CallStatus.in_progress, started=True)

        log.info("Streaming meeting audio for call %s -> room %s (until removed)", call_id, room)

        # Full-fidelity recording is the source of truth. The reader loop below does
        # nothing but pull every PCM frame from parec and write it to the WAV — local
        # disk, so it never backpressures and never drops a word. LiveKit publishing
        # (only powering the live preview) runs on a SEPARATE task fed by a bounded
        # queue; if the network falls behind, we drop the live copy, never the WAV.
        # After the call, the complete WAV is batch-transcribed for the authoritative
        # transcript (see call_processor._rebuild_transcript_from_recording).
        wav_path = recording_path(call_id)
        wav_path.parent.mkdir(parents=True, exist_ok=True)

        publish_q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=200)  # ~2s of 10ms frames

        # Ground-truth speaker attribution: sample Meet's active-speaker signal into a
        # timeline sharing t=0 with the WAV, so voices can be matched to real names
        # after the call instead of guessed. `clock` is marked on the first frame.
        clock = RecordingClock()
        speaker_samples: list[SpeakerSample] = []

        async def _record() -> None:
            wav = wave.open(str(wav_path), "wb")
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(2)  # s16le
            wav.setframerate(SAMPLE_RATE)
            try:
                async for frame in capture.frames():
                    clock.mark_start()  # t=0 of the recording (no-op after the first frame)
                    wav.writeframes(frame)  # lossless: prioritised over publishing
                    try:
                        publish_q.put_nowait(frame)
                    except asyncio.QueueFull:
                        pass  # live preview only — safe to drop, the WAV still has it
            finally:
                wav.close()
                log.info("Saved full meeting recording -> %s", wav_path)
                try:
                    publish_q.put_nowait(None)  # signal the publisher to stop
                except asyncio.QueueFull:
                    pass

        async def _publish() -> None:
            while True:
                frame = await publish_q.get()
                if frame is None:
                    return
                try:
                    await publisher.capture_frame(frame)
                except Exception:
                    log.debug("live publish frame dropped", exc_info=True)

        async def _stream() -> None:
            recorder = asyncio.create_task(_record())
            publisher_task = asyncio.create_task(_publish())
            try:
                await recorder
            finally:
                # On normal EOF the recorder already flushed the WAV and signalled the
                # publisher. On external cancel (bot kicked / End meeting), cancel both
                # so the recorder's finally still runs wav.close() and nothing hangs.
                recorder.cancel()
                publisher_task.cancel()
                await asyncio.gather(recorder, publisher_task, return_exceptions=True)

        # Periodically read the Meet roster so attendees come from the real participant
        # list, not from diarization guesses.
        async def _track_roster() -> None:
            while True:
                try:
                    names = await bot.get_participants()
                    if names:
                        async with SessionLocal() as db:
                            c = await db.get(Call, call_id)
                            if c is not None:
                                merged = sorted(set(c.participants or []) | set(names))
                                if merged != (c.participants or []):
                                    c.participants = merged
                                    await db.commit()
                except Exception:
                    log.debug("roster capture failed", exc_info=True)
                await asyncio.sleep(20)

        # Stay in the meeting and keep streaming until the host kicks the bot out
        # (or the audio stream dies). The bot does NOT leave on its own.
        stream_task = asyncio.create_task(_stream())
        removed_task = asyncio.create_task(bot.wait_until_removed())
        roster_task = asyncio.create_task(_track_roster())
        # Sample who's speaking throughout the call for ground-truth attribution.
        speaker_task = asyncio.create_task(
            track_active_speakers(bot, clock, speaker_samples)
        )
        # Continuously pin the browser's audio onto our capture sink. Without this the
        # meeting audio stays on the host's default device and the recording is silent.
        # Scoped to THIS bot's browser pids so concurrent calls don't mix audio.
        route_task = asyncio.create_task(
            capture.route_loop(pid_provider=bot.browser_pids)
        )
        wait_for = {stream_task, removed_task}
        if stop_event is not None:
            wait_for.add(asyncio.create_task(stop_event.wait()))
        _, pending = await asyncio.wait(wait_for, return_when=asyncio.FIRST_COMPLETED)
        roster_task.cancel()
        speaker_task.cancel()
        route_task.cancel()
        for t in pending:
            t.cancel()
        log.info("Bot session ended for call %s; finalizing", call_id)

        # Persist the active-speaker timeline next to the WAV so process_call can
        # correlate it against the diarized transcript.
        if speaker_samples:
            try:
                speaker_attribution.write_timeline(
                    speaker_attribution.timeline_path(call_id), speaker_samples, 0.5
                )
            except Exception:
                log.warning("failed to write speaker timeline for %s", call_id, exc_info=True)
        else:
            log.info("No active-speaker samples captured for %s (LLM will name speakers)", call_id)

    except Exception:
        log.exception("Bot run failed for call %s", call_id)
        await _set_status(call_id, CallStatus.failed, ended=True)
        raise
    finally:
        if bot is not None:
            await bot.leave()
        await publisher.close()
        await capture.close()
        if slot is not None:
            slot.release()

    # Let the transcription agent flush its final segments after the room closes,
    # then run the call-end pipeline (transcript -> Gemini MOM + scores -> embed).
    await asyncio.sleep(5)
    async with SessionLocal() as db:
        mom = await process_call(db, call_id)
    if mom is not None:
        log.info("MOM ready for call %s:\n%s", call_id, mom.raw_summary)
    else:
        log.warning("No MOM produced for call %s (empty transcript?)", call_id)
