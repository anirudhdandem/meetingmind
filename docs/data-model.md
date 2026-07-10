# Data model

Six core tables. `jsonb` for semi-structured LLM output, `vector` (pgvector) for memory.

## `companies`
Anchor entity. Everything (memory, outcomes, comparison cohorts) keys off `company_id`.

| column | type | notes |
|---|---|---|
| id | uuid pk | |
| name | text | |
| segment | text | for cohort comparison (step 10) |
| created_at | timestamptz | |

## `calls` — call metadata (spec step 4)
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| company_id | uuid fk | |
| sales_rep_id | uuid | |
| meeting_platform | text | zoom / meet / teams (meet first) |
| scheduled_at | timestamptz | |
| started_at / ended_at | timestamptz | |
| status | text | in_progress / completed / failed |
| livekit_room | text | room the bot publishes into |

## `call_transcripts` — live diarized chunks (spec step 3)
Written continuously by the LiveKit agent as Deepgram emits segments. Crash-safe.

| column | type | notes |
|---|---|---|
| id | uuid pk | |
| call_id | uuid fk | |
| speaker_label | text | Deepgram diarization index (anonymous) |
| text | text | |
| start_ts / end_ts | float | seconds from call start |
| confidence | float | |

## `moms` — minutes of meeting (spec step 6, LLM call #1)
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| call_id / company_id | uuid fk | |
| attendees | jsonb | |
| pain_points | jsonb | |
| objections | jsonb | |
| next_steps | text | |
| decision_maker | text | |
| budget_signal | text | |
| raw_summary | text | source for embedding (step 7) |
| created_at | timestamptz | |

## `call_scores` — rubric scores (spec step 8, LLM call #2)
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| call_id | uuid fk | |
| engagement_score | int | |
| objection_severity | int | |
| urgency_score | int | |
| technical_fit_score | int | |
| overall_rating | int | |
| qualitative_notes | text | |

## `lead_outcomes` — ground truth (spec step 9)
Filled in later by CRM/human. Without this, comparison has nothing to compare.

| column | type | notes |
|---|---|---|
| id | uuid pk | |
| company_id / call_id | uuid fk | |
| status | text | accepted / rejected / pending |
| outcome_date | timestamptz | |
| outcome_notes | text | |

## `company_memory` — embeddings (spec step 7)
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| company_id | uuid fk | exact-match lookup for "same company" |
| call_id | uuid fk | |
| embedding | vector(768) | Gemini `gemini-embedding-001` |
| source_text | text | what was embedded (raw_summary + key fields) |
| created_at | timestamptz | |

> Note: "same company" recall is a SQL filter on `company_id`. pgvector similarity is for
> cross-company "calls like this one" (retrieval layer, step 11).
