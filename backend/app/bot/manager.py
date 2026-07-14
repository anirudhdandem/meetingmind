"""In-process registry of running meeting bots, so the API can start/stop them.

The frontend "Start" button kicks off `run_bot_for_call` as an asyncio task on the
API event loop; the "End meeting" button sets the call's stop event, which makes the
bot leave and triggers the call-end pipeline (transcript -> Gemini MOM). This keeps
everything in one process — no extra worker/queue infra for the demo setup.
"""

from __future__ import annotations

import asyncio
import uuid

from app.bot.runner import run_bot_for_call
from app.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.services.call_processor import process_call, recording_path

log = get_logger(__name__)

_tasks: dict[uuid.UUID, asyncio.Task] = {}
_stops: dict[uuid.UUID, asyncio.Event] = {}


def is_running(call_id: uuid.UUID) -> bool:
    task = _tasks.get(call_id)
    return task is not None and not task.done()


def active_count() -> int:
    return sum(1 for task in _tasks.values() if not task.done())


def has_capacity() -> bool:
    """Whether another bot can start (bots run concurrently up to the limit)."""
    return active_count() < get_settings().max_concurrent_bots


async def _run(call_id: uuid.UUID, stop_event: asyncio.Event) -> None:
    try:
        await run_bot_for_call(call_id, stop_event=stop_event)
    except Exception:
        log.exception("bot task crashed for call %s", call_id)
        # A crash must not cost the meeting its minutes: whatever audio reached
        # disk before the crash still gets the full pipeline (idempotent, and a
        # no-op when nothing was recorded — the call just stays failed).
        try:
            if recording_path(call_id).exists():
                async with SessionLocal() as db:
                    await process_call(db, call_id)
        except Exception:
            log.exception("post-crash summarization failed for call %s", call_id)
    finally:
        _tasks.pop(call_id, None)
        _stops.pop(call_id, None)


def start_bot(call_id: uuid.UUID) -> bool:
    """Launch the bot for `call_id`. Returns False if one is already running.

    Raises RuntimeError when `max_concurrent_bots` meetings are already live —
    callers surface that to the user instead of silently queueing.
    """
    if is_running(call_id):
        return False
    if not has_capacity():
        raise RuntimeError(
            f"already in {active_count()} meetings (max_concurrent_bots="
            f"{get_settings().max_concurrent_bots}) — end one first"
        )
    stop_event = asyncio.Event()
    _stops[call_id] = stop_event
    _tasks[call_id] = asyncio.create_task(_run(call_id, stop_event))
    log.info("started bot task for call %s", call_id)
    return True


def stop_bot(call_id: uuid.UUID) -> bool:
    """Signal the bot for `call_id` to leave and finalize. Returns False if not running."""
    stop_event = _stops.get(call_id)
    if stop_event is None:
        return False
    stop_event.set()
    log.info("stop signalled for call %s", call_id)
    return True


async def stop_and_finalize(call_id: uuid.UUID) -> None:
    """End the meeting and guarantee a MOM is produced.

    If the bot is running in this process, signal it to leave and wait for its own
    call-end pipeline (which captures the final flushed transcript). Otherwise — e.g.
    the bot was started from a terminal in another process, or already exited — run the
    summarization pipeline directly on whatever transcript chunks are in the DB. Either
    way the frontend's polling picks up the MOM once it lands.
    """
    task = _tasks.get(call_id)
    if task is not None and not task.done():
        stop_bot(call_id)
        try:
            await task  # runner runs process_call after it leaves + flushes
        except Exception:
            log.exception("bot task failed while finalizing call %s", call_id)
        return

    log.info("no in-process bot for call %s; summarizing captured chunks directly", call_id)
    async with SessionLocal() as db:
        await process_call(db, call_id)
