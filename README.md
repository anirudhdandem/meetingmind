# MeetingMind

Sales-call intelligence platform. A bot joins a Google Meet call, captures audio, transcribes
it live (LiveKit + Deepgram), then extracts minutes-of-meeting, scores the call against a rubric,
remembers it per company, and produces grounded won-vs-lost comparisons (Gemini).

Built from scratch — no managed meeting-bot API.

## Repo layout

```
meetingmind/
├── backend/            # Python: bot, STT agent, LLM pipeline, retrieval API
│   ├── app/
│   │   ├── bot/        # Google Meet join + audio capture
│   │   ├── agent/      # LiveKit agent + Deepgram STT
│   │   ├── services/   # call-end orchestration
│   │   ├── llm/        # Gemini: MOM, scoring, comparison
│   │   ├── embeddings/ # Gemini embeddings + pgvector
│   │   ├── models/     # SQLAlchemy ORM (6 tables)
│   │   ├── api/        # FastAPI retrieval layer + webhooks
│   │   ├── core/       # db session, logging
│   │   └── config.py   # settings
│   ├── migrations/     # Alembic
│   ├── tests/
│   └── requirements.txt
├── frontend/           # dashboard (Next.js — added in phase 4)
├── infra/docker/       # container/runtime assets
├── docs/               # architecture.md, data-model.md
├── docker-compose.yml  # Postgres + pgvector for local dev
└── .env.example
```

## Stack

| layer | choice |
|---|---|
| Meeting join + capture | Playwright + Xvfb + PulseAudio (Google Meet) |
| Media transport | LiveKit Cloud |
| STT | Deepgram (live, diarized) |
| Storage | Postgres + pgvector |
| LLM + embeddings | Gemini |
| API | FastAPI |
| Frontend | Next.js (phase 4) |

See [`docs/architecture.md`](docs/architecture.md) and [`docs/data-model.md`](docs/data-model.md).

## Getting started

```bash
cp .env.example .env          # fill in LiveKit / Deepgram / Gemini keys
docker compose up -d          # Postgres + pgvector

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
# (migrations + run commands land in phase 0/1)
```

## Status

Phase 0 — scaffold in place. Next: implement schema/models + migrations, then the Meet
join proof-of-life (phase 1).
