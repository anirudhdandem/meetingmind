# Architecture

## Pipeline

```
┌─────────────┐   audio track   ┌──────────────┐   transcript   ┌──────────────┐
│  Meet Bot   │ ───────────────▶│ LiveKit Room │ ──────────────▶│  STT Agent   │
│ (Playwright │   (published)   │   (Cloud)    │   (subscribe)  │ + Deepgram   │
│  + Xvfb +   │                 └──────────────┘                └──────┬───────┘
│ PulseAudio) │                                                       │ live chunks
└─────────────┘                                                       ▼
                                                              ┌──────────────┐
                                                              │  Postgres    │
                                                              │ call_        │
                                                              │ transcripts  │
                                                              └──────┬───────┘
   on room close (LiveKit webhook)                                   │
        │                                                            │
        ▼                                                            │
┌──────────────────┐   concat transcript   ┌──────────────┐         │
│  call_processor  │ ─────────────────────▶│   Gemini     │         │
│   (services/)    │                       │ MOM + scores │         │
└────────┬─────────┘                       └──────┬───────┘         │
         │                                        │ structured      │
         │   embed raw_summary                    ▼                 │
         ▼                                 moms / call_scores ◀──────┘
   Gemini embeddings ─▶ pgvector (company_memory)
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│ Retrieval API:  by company  │  by similarity  │  by outcome│
└──────────────────────────────────────────────────────────┘
         │
         ▼
   Gemini comparison (won vs lost, on programmatic rubric diffs) ─▶ frontend
```

## Component → folder map (`backend/app/`)

| folder | responsibility |
|---|---|
| `bot/` | Join Google Meet (Playwright/Xvfb), capture mixed audio (PulseAudio), publish to LiveKit |
| `agent/` | LiveKit Agent: subscribe to audio, run Deepgram STT, write `call_transcripts` live |
| `services/` | `call_processor` — call-end orchestration (concat → LLM → embed) |
| `llm/` | Gemini: MOM extraction, rubric scoring, comparative analysis |
| `embeddings/` | Gemini embeddings + pgvector upsert/query |
| `models/` | SQLAlchemy ORM (the six tables in `data-model.md`) |
| `api/routes/` | Retrieval layer + call CRUD + LiveKit webhook receiver |
| `core/` | DB session, logging |

## Key decisions

- **From-scratch bot, no managed meeting-bot API.** Trade-off accepted: single *mixed*
  audio stream (diarization is the only speaker separation), host must admit the bot,
  UI-change maintenance burden.
- **Google Meet first.** Easiest to automate; Zoom/Teams port the join logic later.
- **LiveKit Cloud** (key/secret/URL provided) — no self-hosted media server.
- **Gemini for both LLM and embeddings** — single AI vendor.
- **Cheap work continuous, expensive work batched** — capture/STT/chunk-writes stream
  live; the (paid) LLM runs once at call-end. MOM + scoring share one prompt, two sections.
- **Comparison diffs numbers programmatically before the LLM sees them** — grounds the
  analysis, avoids hallucinated causal stories.

## Build phases

0. Schema + skeleton (this scaffold) — Postgres+pgvector, models, migrations, API skeleton.
1. **Meet join proof-of-life** — bot joins, audio flows, live transcript in console.
2. Call-end → Gemini (MOM + scores) → structured tables.
3. Memory + retrieval (embeddings, pgvector, retrieval API, outcome ingestion).
4. Comparative analysis (programmatic diff → grounded report) + frontend dashboard.
