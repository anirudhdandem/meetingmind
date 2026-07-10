"""Sample Meet's active-speaker signal into a timeline aligned to the WAV recording.

The recording and this tracker run in the same event loop, so they share one
monotonic clock. `RecordingClock` is marked the instant the first PCM frame is
written to the WAV (t=0 of the recording). Every speaker sample is then stamped
`loop.time() - t0`, i.e. seconds into the recording — the exact axis Deepgram's
utterance timestamps use — so the two can be correlated after the call.
"""

from __future__ import annotations

import asyncio

from app.bot.meet_bot import MeetBot
from app.core.logging import get_logger
from app.services.speaker_attribution import SpeakerSample

log = get_logger(__name__)


class RecordingClock:
    """Shared t=0 marker between the WAV recorder and the speaker tracker."""

    def __init__(self) -> None:
        self._t0: float | None = None
        self.started = asyncio.Event()

    def mark_start(self) -> None:
        """Call once, when the first audio frame hits the WAV."""
        if self._t0 is None:
            self._t0 = asyncio.get_event_loop().time()
            self.started.set()

    @property
    def t0(self) -> float | None:
        return self._t0


async def track_active_speakers(
    bot: MeetBot,
    clock: RecordingClock,
    samples: list[SpeakerSample],
    interval: float = 0.5,
) -> None:
    """Poll 'who is speaking now' every `interval`s, appending to `samples`.

    Runs for the life of the call (cancelled at the end). Waits for the recording to
    start so sample timestamps share the WAV's t=0. Best-effort throughout: turns on
    captions once, then samples; any error is swallowed so it never disrupts the call.
    """
    await clock.started.wait()
    try:
        await bot.enable_captions()
    except Exception:
        log.debug("could not enable captions", exc_info=True)

    while True:
        try:
            t0 = clock.t0
            if t0 is not None:
                names = await bot.get_active_speakers()
                if names:
                    t = asyncio.get_event_loop().time() - t0
                    samples.append(SpeakerSample(t=t, speakers=names))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.debug("active-speaker sample failed", exc_info=True)
        await asyncio.sleep(interval)
