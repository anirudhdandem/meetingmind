"""Launch the meeting bot for a given call.

    python -m scripts.run_bot <call_id>

Prereqs on the host: PulseAudio running, an X display (Xvfb on servers), and
`playwright install chromium` already run.
"""

import asyncio
import sys
import uuid

from app.bot.runner import run_bot_for_call


async def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m scripts.run_bot <call_id>")
        raise SystemExit(2)
    call_id = uuid.UUID(sys.argv[1])
    await run_bot_for_call(call_id)


if __name__ == "__main__":
    asyncio.run(main())
