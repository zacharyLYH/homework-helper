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
| users, subjects, chats, messages, auth/log tables | concept graph, learner memory state, memory versions, memory jobs, retrieval traces |

Memory tables should not be created in the main app database.

## Table Details

### concepts

Purpose: canonical concept registry.

Why it exists: provides stable concept identities so aliases, graph edges, and learner state can reference the same concept.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key for references from other tables | INTEGER, auto increment | 17 |
| concept_key | Stable machine-readable concept identifier | TEXT, unique, not null, snake_case style | quadratic_formula |
| display_name | Human-readable concept name | TEXT, not null | Quadratic Formula |
| created_at | Record creation timestamp | TEXT, SQLite datetime string | 2026-08-04 12:10:03 |

### concept_aliases

Purpose: alternate labels for concepts.

Why it exists: improves retrieval and matching when users use different words for the same concept.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 8 |
| concept_id | Links alias to one row in concepts | INTEGER, foreign key to concepts.id, not null | 17 |
| alias | Alternate name text | TEXT, unique, not null | quadratic equation formula |
| created_at | Record creation timestamp | TEXT, SQLite datetime string | 2026-08-04 12:11:55 |

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

Why it exists: preserves concrete learning signals that can be summarized into state later.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 31 |
| user_id | Learner identity from app domain | INTEGER, not null | 4 |
| subject_id | Subject/course scope from app domain | INTEGER, not null | 12 |
| observation | Raw observation text | TEXT, not null | Misses sign when expanding binomials |
| source | Origin of observation | TEXT, nullable | chat |
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
| mastery | Estimated mastery score | REAL, default 0.0, usually normalized | 0.62 |
| confidence | Confidence in mastery estimate | REAL, default 0.0, usually normalized | 0.71 |
| updated_at | Last update timestamp | TEXT, SQLite datetime string | 2026-08-04 12:19:20 |

### learner_traits

Purpose: stable learner preferences and habits.

Why it exists: stores personalization hints that are not tied to a single concept state row.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 6 |
| user_id | Learner identity | INTEGER, not null | 4 |
| subject_id | Subject scope | INTEGER, not null | 12 |
| trait_key | Trait name | TEXT, not null, unique with user_id + subject_id | prefers_step_by_step |
| trait_value | Trait value payload | TEXT, not null | true |
| updated_at | Last update timestamp | TEXT, SQLite datetime string | 2026-08-04 12:22:07 |

### memory_versions

Purpose: history of memory summaries per learner/subject.

Why it exists: supports versioned evolution, auditing, and recovery.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 19 |
| user_id | Learner identity | INTEGER, not null | 4 |
| subject_id | Subject scope | INTEGER, not null | 12 |
| version | Monotonic version number per learner/subject | INTEGER, not null, unique with user_id + subject_id | 3 |
| summary | Materialized summary text | TEXT, nullable | Strong with factoring, weak on discriminant |
| created_at | Record creation timestamp | TEXT, SQLite datetime string | 2026-08-04 12:24:39 |

### memory_current

Purpose: pointer to active version for each learner/subject.

Why it exists: gives a single fast lookup for the current memory view.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 7 |
| user_id | Learner identity | INTEGER, not null, unique with subject_id | 4 |
| subject_id | Subject scope | INTEGER, not null, unique with user_id | 12 |
| version_id | Active version row id | INTEGER, foreign key to memory_versions.id, not null | 19 |
| updated_at | Last pointer update timestamp | TEXT, SQLite datetime string | 2026-08-04 12:25:01 |

### memory_update_jobs

Purpose: queue of memory processing work.

Why it exists: decouples memory updates from chat request latency and enables worker processing.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 42 |
| user_id | Learner identity | INTEGER, not null | 4 |
| subject_id | Subject scope | INTEGER, not null | 12 |
| chat_id | Optional originating chat reference | INTEGER, nullable | 98 |
| status | Job lifecycle state | TEXT, not null, default pending | pending, running, done, failed |
| payload_json | Serialized work payload | TEXT, nullable JSON string | {"trigger":"chat_turn","message_id":456} |
| created_at | Job creation timestamp | TEXT, SQLite datetime string | 2026-08-04 12:27:18 |
| updated_at | Last status update timestamp | TEXT, SQLite datetime string | 2026-08-04 12:27:18 |

### retrieval_traces

Purpose: trace logs for retrieval behavior.

Why it exists: supports debugging, quality checks, and offline evaluation.

| Key | What the key is for | Value type and expected content | Example |
|---|---|---|---|
| id | Internal primary key | INTEGER, auto increment | 11 |
| user_id | Learner identity | INTEGER, not null | 4 |
| subject_id | Subject scope | INTEGER, not null | 12 |
| query_text | Retrieval query text | TEXT, not null | explain discriminant intuition |
| result_json | Serialized retrieval result payload | TEXT, nullable JSON string | {"hits":[{"concept_key":"quadratic_formula"}]} |
| created_at | Trace creation timestamp | TEXT, SQLite datetime string | 2026-08-04 12:29:50 |
