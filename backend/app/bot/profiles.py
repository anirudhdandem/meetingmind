"""Per-bot Chromium profile slots so several bots can be in meetings at once.

Chromium hard-locks its user-data-dir (ProcessSingleton), so two concurrent bots
can never share the one signed-in profile in `bot_user_data_dir`. Instead we keep
a small pool of slot directories next to it, each seeded by copying the master
profile — the copy carries the Google session cookies, so every slot is already
signed in and no extra Google accounts are needed. Slots persist and are reused
across runs, so each stays signed in after its first use.

Acquisition takes an exclusive flock on a per-slot lock file, which is safe across
processes: bots managed by the API and ones launched via `scripts/run_bot.py`
can't grab the same slot.
"""

from __future__ import annotations

import fcntl
import os
import shutil
from pathlib import Path

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Chromium lock files that must never be copied into a slot (they'd make the new
# profile look "in use") and are cleared again before every launch in case a
# previous run crashed without cleaning up.
_LOCK_FILES = ("SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile")
# Pure caches — skipping them keeps the seed copy small and fast.
_CACHE_DIRS = (
    "Cache", "Code Cache", "GPUCache", "GrShaderCache", "ShaderCache",
    "Crashpad", "Crash Reports",
)


class ProfileSlot:
    """A reserved profile directory; call `release()` when the bot is done."""

    def __init__(self, path: Path, lock_fd: int) -> None:
        self.path = path
        self._lock_fd = lock_fd

    def release(self) -> None:
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(self._lock_fd)
        log.info("Released bot profile slot %s", self.path)


def _seed(master: Path, slot: Path) -> None:
    if slot.exists():
        return
    if master.is_dir():
        log.info("Seeding bot profile slot %s from %s (copies the Google session)", slot, master)
        # Copy to a scratch dir and rename into place, so a copy that dies halfway
        # (out of disk — each slot is ~0.5GB, and raising MAX_CONCURRENT_BOTS adds
        # one slot each) can't leave a half-seeded, signed-out profile behind that
        # the `slot.exists()` check above would then reuse forever.
        staging = slot.with_name(f"{slot.name}.seeding")
        shutil.rmtree(staging, ignore_errors=True)
        try:
            shutil.copytree(
                master,
                staging,
                ignore=shutil.ignore_patterns(*_LOCK_FILES, *_CACHE_DIRS),
            )
        except OSError:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        staging.rename(slot)
    else:
        # No master profile yet: start empty; MeetBot signs in with the
        # configured credentials on first use.
        slot.mkdir(parents=True, exist_ok=True)


def _clear_stale_locks(slot: Path) -> None:
    for name in _LOCK_FILES:
        try:
            (slot / name).unlink(missing_ok=True)
        except OSError:
            pass


def acquire() -> ProfileSlot:
    """Reserve a free profile slot, creating and seeding it if needed.

    Blocking (does filesystem copies) — call via `asyncio.to_thread` from async
    code. Raises RuntimeError when every slot is busy, i.e. the host is already
    in `max_concurrent_bots` meetings.
    """
    settings = get_settings()
    master = Path(settings.bot_user_data_dir).resolve()
    pool = master.parent / f"{master.name}_slots"
    pool.mkdir(parents=True, exist_ok=True)

    for i in range(settings.max_concurrent_bots):
        fd = os.open(pool / f"slot-{i}.lock", os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            continue  # slot busy — another bot holds it
        slot = pool / f"slot-{i}"
        try:
            _seed(master, slot)
            _clear_stale_locks(slot)
        except Exception:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            raise
        log.info("Acquired bot profile slot %s", slot)
        return ProfileSlot(slot, fd)

    raise RuntimeError(
        f"all {settings.max_concurrent_bots} bot profile slots are in use — "
        "end a meeting first or raise MAX_CONCURRENT_BOTS"
    )
