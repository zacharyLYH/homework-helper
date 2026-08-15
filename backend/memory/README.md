# Memory Package Database Schemas

This folder owns the standalone memory database schema and runtime helpers.
Source of truth is [db.py](db.py).

## Bootstrap
Run once to create empty memory.db with schema tables initialized
```
cd ./homework-helper/backend
uv run python -c "from memory.db import init_db; print(init_db())"
```

## Seed (optional)
Apply deterministic starter rows for local memory testing.
```
cd ./homework-helper/backend
uv run python -m memory.seed
```

## Worker
Run one-shot processing (useful in tests and local checks).
```
cd ./homework-helper/backend
uv run python -m memory.jobs --once
```

Run long-lived worker loop.
```
cd ./homework-helper/backend
uv run python -m memory.jobs --poll-interval 2 --batch-size 20
```

## Why this database is separate

| Decision | Why |
|---|---|
| Separate SQLite file for memory | Keeps chat/auth app data independent from memory schema changes and memory-specific load. |
| Schema ownership inside this package | Keeps memory table contracts close to memory service logic. |
| Idempotent bootstrap (`CREATE TABLE IF NOT EXISTS`) | Safe repeated initialization in startup and tests. |

## Boundary with main app DB

| Lives in app DB | Lives in memory DB |
|---|---|
| users, subjects, chats, messages, auth/log tables | concept graph, learner state, memory summary, memory jobs, retrieval traces |

Memory tables should not be created in the main app database.

## Data flow

```
Chat turn
  └─▶ service.enqueue_memory_update()   ← writes memory_update_jobs (pending)
        └─▶ worker claims job           ← updates status: pending → running
              ├─▶ insert learner_observations
              ├─▶ upsert memory_summary
              └─▶ status: done / failed

Graph read path (per turn):
  load_memory_context() → reads memory_summary → falls back to learner_observations
```

`user_id`, `subject_id`, and `chat_id` are referenced by value from the main app DB — no foreign keys cross the DB boundary.

## Schema changes (redesign)

Three tables were removed and their data consolidated:

| Removed | Replaced by | Reason |
|---|---|---|
| `concept_aliases` | `concepts.aliases` (JSON array column) | Aliases are always read with their concept; a join table was unnecessary overhead |
| `memory_versions` | `memory_summary` | Version history was not consumed at runtime; current state only is sufficient |
| `memory_current` | `memory_summary` | The pointer indirection (`memory_current → memory_versions`) collapsed into a single upsertable row |

`concepts` gained a `subject_id` column so concept keys are scoped per subject and no longer collide across courses.

`learner_traits` changed from one row per trait (`trait_key`, `trait_value`) to one row per learner/subject scope (`traits_json`), since all traits are always read and written together.

## Table Details

### concepts

Purpose: canonical concept registry, scoped by subject.

Why it exists: provides stable concept identities so graph edges and learner state can reference the same concept without key collisions across subjects.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key for references from other tables | INTEGER, auto increment | 17 |
| subject_id | Subject scope from app domain | INTEGER, not null | 12 |
| concept_key | Stable machine-readable concept identifier, unique per subject | TEXT, not null, snake_case style | quadratic_formula |
| display_name | Human-readable concept name | TEXT, not null | Quadratic Formula |
| aliases | Alternate names for matching and retrieval | TEXT, JSON array, default '[]' | ["quadratic equation formula"] |
| created_at | Record creation timestamp | TEXT, SQLite datetime string | 2026-08-04 12:10:03 |

### concept_edges

Purpose: directed relationships between concepts.

Why it exists: models prerequisite or semantic edges for concept-aware retrieval and progression.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 5 |
| from_concept_id | Edge source concept | INTEGER, foreign key to concepts.id, not null | 17 |
| to_concept_id | Edge destination concept | INTEGER, foreign key to concepts.id, not null | 9 |
| relation | Relationship label | TEXT, not null | prerequisite |
| weight | Strength of the relation | REAL, default 1.0 | 0.75 |
| created_at | Record creation timestamp | TEXT, SQLite datetime string | 2026-08-04 12:14:01 |

### learner_observations

Purpose: append-only evidence from interactions.

Why it exists: preserves concrete learning signals that feed the memory summary.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 31 |
| user_id | Learner identity from app domain | INTEGER, not null | 4 |
| subject_id | Subject/course scope from app domain | INTEGER, not null | 12 |
| observation | Raw observation text | TEXT, not null | Misses sign when expanding binomials |
| source | Origin of observation | TEXT, nullable | memory_worker |
| created_at | Record creation timestamp | TEXT, SQLite datetime string | 2026-08-04 12:16:48 |

### learner_concept_state

Purpose: current concept-level learner mastery snapshot.

Why it exists: fast read model for personalization without scanning all observations.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 14 |
| user_id | Learner identity | INTEGER, not null | 4 |
| subject_id | Subject scope | INTEGER, not null | 12 |
| concept_id | Linked concept | INTEGER, foreign key to concepts.id, not null | 17 |
| mastery | Estimated mastery score | REAL, default 0.0, range 0.0–1.0 | 0.62 |
| confidence | Confidence in mastery estimate | REAL, default 0.0, range 0.0–1.0 | 0.71 |
| updated_at | Last update timestamp | TEXT, SQLite datetime string | 2026-08-04 12:19:20 |

### learner_traits

Purpose: stable learner preferences and habits per scope.

Why it exists: stores personalization hints as a single JSON blob; all traits are always read and written together so per-row storage was unnecessary.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 6 |
| user_id | Learner identity | INTEGER, not null | 4 |
| subject_id | Subject scope | INTEGER, not null | 12 |
| traits_json | All traits for this learner/subject | TEXT, JSON object, default '{}' | {"prefers_step_by_step": true} |
| updated_at | Last update timestamp | TEXT, SQLite datetime string | 2026-08-04 12:22:07 |

### memory_summary

Purpose: current materialized summary per learner/subject.

Why it exists: single upsertable row gives a fast read path for `load_memory_context` without join indirection. Replaces the old `memory_versions` + `memory_current` two-table design.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 7 |
| user_id | Learner identity | INTEGER, not null | 4 |
| subject_id | Subject scope | INTEGER, not null | 12 |
| summary | LLM-generated summary of learner state | TEXT, default '' | Strong with factoring, weak on discriminant |
| updated_at | Last write timestamp | TEXT, SQLite datetime string | 2026-08-04 12:25:01 |

### memory_update_jobs

Purpose: queue of memory processing work.

Why it exists: decouples memory updates from chat request latency and enables async worker processing.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 42 |
| user_id | Learner identity | INTEGER, not null | 4 |
| subject_id | Subject scope | INTEGER, not null | 12 |
| chat_id | Optional originating chat reference | INTEGER, nullable | 98 |
| status | Job lifecycle state | TEXT, not null, default pending | pending, running, done, failed |
| payload_json | Serialized turn snippet and context | TEXT, nullable JSON string | {"trigger":"chat_turn","messages":[...]} |
| created_at | Job creation timestamp | TEXT, SQLite datetime string | 2026-08-04 12:27:18 |
| updated_at | Last status update timestamp | TEXT, SQLite datetime string | 2026-08-04 12:27:18 |

### retrieval_traces

Purpose: trace logs for retrieval behavior.

Why it exists: supports debugging and offline evaluation; never read at runtime.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 11 |
| user_id | Learner identity | INTEGER, not null | 4 |
| subject_id | Subject scope | INTEGER, not null | 12 |
| query_text | Description of what was requested | TEXT, not null | explain discriminant intuition |
| result_json | Sections returned (summary presence, weak concept count, etc.) | TEXT, nullable JSON string | {"summary_present":true,"weak_concept_count":2} |
| created_at | Trace creation timestamp | TEXT, SQLite datetime string | 2026-08-04 12:29:50 |
