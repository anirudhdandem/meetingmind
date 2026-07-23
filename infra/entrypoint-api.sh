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
  # A daemon killed without cleanup — OOM, or the disk filling under it — leaves its
  # pid file and socket behind, and `pulseaudio --start` then declines to start
  # because it believes one is already running. Every meeting after that records
  # silence while the logs look perfectly healthy, so clear the corpse first. Only
  # reached when no daemon answers, i.e. the files cannot belong to a live one.
  if [ -e "$XDG_RUNTIME_DIR/pulse/pid" ] || [ -e "$XDG_RUNTIME_DIR/pulse/native" ]; then
    echo "[entrypoint] clearing stale PulseAudio state (no daemon is answering)"
    pkill -x pulseaudio 2>/dev/null || true
    sleep 1
    rm -f "$XDG_RUNTIME_DIR/pulse/pid" "$XDG_RUNTIME_DIR/pulse/native"
  fi

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

# 0001_initial builds the schema with `Base.metadata.create_all`, i.e. from today's
# models — so on an empty database it already produces the *head* schema, and 0002+
# then fail trying to add columns that exist ("column points_discussed ... already
# exists"). Run 0001 alone (it also installs pgvector and the HNSW index) and stamp
# head. Safe because every table in the models is head-state: recovery_codes is
# dropped by 0014/0015, and 0015's data statements are no-ops on an empty DB.
# An already-migrated database takes the normal path.
if alembic current 2>/dev/null | grep -qE '[0-9a-f_]+ \(head\)|[0-9]{4}_'; then
  echo "[entrypoint] existing database — running migrations"
  alembic upgrade head
else
  echo "[entrypoint] empty database — creating schema, stamping head"
  alembic upgrade 0001_initial
  alembic stamp head
fi

# ONE worker, always. Running bots live in this process's memory (app/bot/manager.py
# keeps `_tasks` / `_stops` dicts), so a second worker could not see — let alone stop —
# a bot started by the first. Scale concurrency with MAX_CONCURRENT_BOTS, not workers.
echo "[entrypoint] starting API"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 "$@"
