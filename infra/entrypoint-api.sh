#!/usr/bin/env bash
# Bring up the audio stack, migrate, then serve.
#
# Xvfb is deliberately NOT started here — app/bot/display.py spawns it on the first bot
# join, so the containerized and bare-VM paths run identical code. PulseAudio, though,
# must already exist before any bot tries to create its null sink.
set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime}"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

if ! pactl info >/dev/null 2>&1; then
  echo "[entrypoint] starting PulseAudio"
  # --exit-idle-time=-1: never self-terminate between meetings.
  pulseaudio --start --exit-idle-time=-1 --disallow-exit >/dev/null 2>&1 || true

  for _ in $(seq 1 20); do
    pactl info >/dev/null 2>&1 && break
    sleep 0.25
  done
fi

if pactl info >/dev/null 2>&1; then
  echo "[entrypoint] PulseAudio ready"
else
  echo "[entrypoint] WARNING: PulseAudio did not come up — meetings will record silence" >&2
fi

echo "[entrypoint] running database migrations"
alembic upgrade head

# ONE worker, always. Running bots live in this process's memory (app/bot/manager.py
# keeps `_tasks` / `_stops` dicts), so a second worker could not see — let alone stop —
# a bot started by the first. Scale concurrency with MAX_CONCURRENT_BOTS, not workers.
echo "[entrypoint] starting API"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 "$@"
