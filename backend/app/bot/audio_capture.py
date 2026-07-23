"""Capture meeting audio on Linux via a PulseAudio null-sink monitor.

The browser plays the meeting audio into a virtual sink; we record that sink's `.monitor`
source with `parec` and yield raw PCM frames. This gives a single MIXED stream of everyone
in the call (per-speaker separation is left to Deepgram diarization downstream).
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import AsyncIterator, Callable

from app.core.logging import get_logger

log = get_logger(__name__)


def _descendant_pids(root: int) -> set[int]:
    """All PIDs in `root`'s process subtree (so we only touch the bot's own browser)."""
    children: dict[int, list[int]] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "rb") as f:
                data = f.read()
            # /proc/<pid>/stat: "pid (comm) state ppid ..." — comm may contain spaces
            # and parens, so split after the last ')'.
            ppid = int(data[data.rfind(b")") + 2 :].split()[1])
        except (OSError, IndexError, ValueError):
            continue
        children.setdefault(ppid, []).append(int(entry))
    out: set[int] = {root}
    stack = [root]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out

# Audio format shared across capture -> LiveKit publish -> Deepgram.
SAMPLE_RATE = 48000
CHANNELS = 1
FRAME_MS = 10
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000           # 480 samples / 10ms
FRAME_BYTES = FRAME_SAMPLES * CHANNELS * 2               # s16le -> 2 bytes/sample



async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {err.decode().strip()}")
    return out.decode().strip()


class PulseAudioCapture:
    """Creates a virtual sink, makes it default, and streams its monitor as PCM frames."""

    def __init__(self, sink_name: str | None = None) -> None:
        # Unique per capture so concurrent bots (same process or not) each get
        # their own sink — a shared name would mix every meeting into one stream.
        self.sink_name = sink_name or f"mm_sink_{uuid.uuid4().hex[:8]}"
        self._module_id: str | None = None
        self._proc: asyncio.subprocess.Process | None = None

    async def setup(self) -> None:
        """Load the null sink the bot records from.

        We deliberately DO NOT change the system default sink: doing so hijacks the
        host's audio output (and, on Bluetooth, breaks the linked mic so others can't
        hear the human on this machine). The bot's own browser audio is routed into
        this sink per-stream by `pin_inputs()`/`route_loop()`, which leaves every other
        app — including the user's own Meet tab and their devices — untouched.
        """
        self._module_id = await _run(
            "pactl", "load-module", "module-null-sink",
            f"sink_name={self.sink_name}",
            "sink_properties=device.description=Fennec",
        )
        log.info("PulseAudio sink %s ready (module %s)", self.sink_name, self._module_id)

    async def pin_inputs(self, pids: set[int] | None = None) -> int:
        """Move the bot browser's playback streams onto our sink so they get recorded.

        We never change the system default sink (that disrupts the host's audio), so the
        bot's Chromium initially plays to whatever device is default. This moves just its
        stream onto our recording sink. Chromium creates that stream only once Meet plays
        audio, so this must be called repeatedly during the call.

        `pids` scopes which streams belong to THIS capture — pass the bot's own browser
        process tree (see MeetBot.browser_pids) so concurrent bots don't steal each
        other's meeting audio. Without it, falls back to this process's whole subtree,
        which is only safe when a single bot runs in the process. Either way the user's
        other audio — including their own Meet tab — is never hijacked into the
        recording sink. Returns how many streams it moved.
        """
        ours = pids if pids is not None else _descendant_pids(os.getpid())
        if not ours:
            return 0
        try:
            out = await _run("pactl", "list", "sink-inputs")
        except RuntimeError:
            return 0
        moved = 0
        for block in out.split("Sink Input #")[1:]:
            index = block.split("\n", 1)[0].strip()
            if not index.isdigit():
                continue
            m = re.search(r'application\.process\.id = "(\d+)"', block)
            if not m or int(m.group(1)) not in ours:
                continue  # not the bot's browser — leave it alone
            try:
                await _run("pactl", "move-sink-input", index, self.sink_name)
                moved += 1
            except RuntimeError:
                pass  # stream may have ended or already be on our sink
        return moved

    async def route_loop(
        self,
        interval: float = 2.0,
        pid_provider: Callable[[], set[int]] | None = None,
    ) -> None:
        """Keep this bot's playback streams pinned to our sink for the whole call.

        `pid_provider` is re-evaluated on every pass because Chromium spawns and
        replaces its audio processes over time.
        """
        last = -1
        while True:
            try:
                pids = pid_provider() if pid_provider is not None else None
                n = await self.pin_inputs(pids)
                if n != last:
                    log.info("Routed %d playback stream(s) into %s", n, self.sink_name)
                    last = n
            except Exception:
                log.debug("audio routing pass failed", exc_info=True)
            await asyncio.sleep(interval)

    async def frames(self) -> AsyncIterator[bytes]:
        """Yield fixed-size s16le PCM frames captured from the sink monitor."""
        self._proc = await asyncio.create_subprocess_exec(
            "parec",
            f"--device={self.sink_name}.monitor",
            "--format=s16le",
            f"--rate={SAMPLE_RATE}",
            f"--channels={CHANNELS}",
            "--raw",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert self._proc.stdout is not None
        log.info("parec capture started on %s.monitor", self.sink_name)
        while True:
            try:
                chunk = await self._proc.stdout.readexactly(FRAME_BYTES)
            except asyncio.IncompleteReadError as e:
                # parec exited mid-frame: emit the trailing partial frame so the
                # final fraction of a second isn't dropped, then stop.
                if e.partial:
                    yield e.partial
                break
            yield chunk

    async def close(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._proc.kill()
        if self._module_id:
            try:
                await _run("pactl", "unload-module", self._module_id)
            except RuntimeError:
                pass
        log.info("PulseAudio capture closed")
