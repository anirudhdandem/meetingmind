"""A virtual X display for the meeting bot, so Chromium never opens a real window.

Meet fingerprints headless Chromium and behaves badly under it (and a headless browser
produces no PulseAudio sink-inputs, which is exactly what `audio_capture` records). So
the bot always runs a *headful* browser — and on a server, points it at an Xvfb virtual
framebuffer instead of a physical screen. No monitor, no window, same browser.

`ensure_display()` is idempotent and safe to call from every bot start:

  * `DISPLAY` already set (a developer's desktop, or an entrypoint that started Xvfb)
    -> use it, start nothing.
  * `use_xvfb` off -> do nothing; Chromium will use whatever DISPLAY exists, and will
    fail loudly if there is none. That is the correct outcome for a misconfigured host.
  * otherwise -> spawn one Xvfb for the process lifetime and export its DISPLAY.

The Xvfb process is shared by every concurrent bot (they're separate Chromium profiles
on one display, never visible to anyone) and is reaped at interpreter exit.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import threading
import time

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Matches the browser viewport in meet_bot.py, with room for Chrome's own chrome.
_SCREEN = "1280x720x24"
# Xvfb writes its display number here once it's actually accepting connections;
# racing straight into Chromium otherwise yields "cannot open display".
_READY_TIMEOUT_SECONDS = 10.0

_lock = threading.Lock()
_process: subprocess.Popen | None = None


def _display_is_up(display: str) -> bool:
    """Whether an X server is listening on `display` (e.g. ':99')."""
    # Xvfb creates this socket once it is ready to serve.
    return os.path.exists(f"/tmp/.X11-unix/X{display.lstrip(':')}")


def _shutdown() -> None:
    global _process
    if _process is None or _process.poll() is not None:
        return
    log.info("Stopping Xvfb (pid %s)", _process.pid)
    _process.terminate()
    try:
        _process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _process.kill()
    _process = None


def ensure_display() -> str | None:
    """Guarantee a usable DISPLAY for a headful browser. Returns it, or None.

    Raises RuntimeError if Xvfb is wanted but unusable — failing at bot start with a
    clear message beats Chromium dying with an opaque one 30 seconds later.
    """
    global _process

    existing = os.environ.get("DISPLAY")
    if existing:
        return existing

    if not get_settings().use_xvfb:
        log.warning(
            "No DISPLAY set and USE_XVFB is off — a headful Chromium cannot start. "
            "Set USE_XVFB=true on servers."
        )
        return None

    with _lock:
        # Another bot may have started it while we waited for the lock.
        if _process is not None and _process.poll() is None:
            return os.environ["DISPLAY"]

        if shutil.which("Xvfb") is None:
            raise RuntimeError(
                "USE_XVFB is on but the Xvfb binary is missing. "
                "Install it (Debian/Ubuntu: apt-get install -y xvfb)."
            )

        display = os.environ.get("XVFB_DISPLAY", ":99")
        if _display_is_up(display):
            # Someone (a container entrypoint) already runs one; adopt it.
            log.info("Reusing existing X server on %s", display)
            os.environ["DISPLAY"] = display
            return display

        log.info("Starting Xvfb on %s (%s)", display, _SCREEN)
        _process = subprocess.Popen(
            ["Xvfb", display, "-screen", "0", _SCREEN, "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        atexit.register(_shutdown)

        deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if _process.poll() is not None:
                raise RuntimeError(f"Xvfb exited immediately (code {_process.returncode})")
            if _display_is_up(display):
                os.environ["DISPLAY"] = display
                log.info("Xvfb ready on %s (pid %s)", display, _process.pid)
                return display
            time.sleep(0.1)

        _shutdown()
        raise RuntimeError(f"Xvfb did not become ready on {display} within {_READY_TIMEOUT_SECONDS}s")
