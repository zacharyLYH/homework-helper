# Stage 08: Backend - Standalone Memory Subsystem (Reworked)

**Sequence:** 8 of 8  
**Status:** Completed (updated after Commit 6)

## Scope
- `backend/memory/`
- `backend/app/config.py`
- `backend/app/graph.py`
- `backend/app/routes/chat.py`
- `backend/app/main.py`
- `backend/tests/`
- `data/` (memory DB bootstrap and seed)

## Goal
Introduce a standalone memory subsystem with its own SQLite DB file, optional runtime enablement via `.env`, and safe default behavior that keeps memory off when memory data is unavailable.

---

## Completion Snapshot (After Commit 5)

| Work item | Status | Notes |
|---|---|---|
| 8.1 Runtime config and feature gate | Completed | `MEMORY_ENABLED` and `MEMORY_STRICT_MODE` are wired; startup gate enforces strict/non-strict behavior. |
| 8.2 Standalone package structure | Completed | `backend/memory/{config,db,schemas,service,jobs,routes}.py` exists. |
| 8.3 Separate memory DB and schema bootstrap | Completed | Dedicated connector + schema bootstrap in `memory/db.py`; main DB does not create memory tables. |
| 8.4 Graph simplification (single responder + memory hooks) | Completed | Graph now wraps the existing `agent <-> tool_executor` loop with `memory_loader` and `memory_updater`. |
| 8.5 Memory integration points | Completed | `memory_loader` and `memory_updater` are wired with best-effort behavior and failure swallowing. |
| 8.6 Memory HTTP routes ownership | Completed | Memory routes are owned under `backend/memory/routes.py`, mounted always, and enforce disabled `503` contract. |
| 8.7 Chat route integration | Completed | Chat route now passes `user_id`, `subject_id`, `memory_context`, `memory_loaded`, and runtime `memory_enabled` into graph state. |
| 8.8 Seed and local run workflow | Completed | Added `memory.seed` CLI and deterministic seed SQL (`data/memory-seed.sql`) plus runbook commands. |
| 8.9 Tests | Completed | Added worker integration tests for success path and failure isolation; prior runtime/graph/routes coverage retained. |
| 8.10 Verification | Completed | Commit 6 focused verification executed including worker tests and memory/chat regressions. |

---

## Current Implemented Architecture

```text
Main app DB (existing)         users, subjects, chats, messages
Memory DB (implemented)        concepts, aliases, edges, observations, state, versions, jobs, traces
Memory package (implemented)   backend/memory/{config,db,schemas,service,jobs,routes}
Runtime gate (implemented)     MEMORY_ENABLED + MEMORY_STRICT_MODE + schema presence checks
Default memory DB path         data/memory.db (repo top-level)
Graph integration              implemented (optional memory_loader/memory_updater around existing loop)
```

Design principle remains unchanged: memory is additive and chat must remain healthy when memory is disabled.

---

## Guidelines (STRICT)

1. Do not block chat responses on memory failures.
2. Do not store memory tables in the main app DB.
3. Keep mode-based responder branching removed.
4. Memory default stays OFF unless explicitly enabled and available.
5. If memory is requested ON but unavailable, strict mode fails startup; non-strict mode auto-disables memory.
6. Keep memory writes append-only where applicable (observations, versions, traces).
7. Keep memory DB initialization and migrations inside `backend/memory` ownership.
8. Validate both runtime profiles in tests: memory OFF and memory ON.

---

## Work Items and Status Detail

### 8.1 Runtime config and feature gate - Completed

Implemented:
- `MEMORY_ENABLED=false` default.
- `MEMORY_STRICT_MODE=true` default.
- Canonical runtime capability check in memory service.
- Startup enforcement in app lifespan.

Behavior implemented:
- `enabled=false` when env flag is off.
- `enabled=true` only when memory DB exists and required tables exist.
- Requested ON + unavailable:
  - strict mode true: startup failure
  - strict mode false: auto-disable and continue

### 8.2 Standalone package structure - Completed

Implemented package:

```text
backend/memory/
  __init__.py
  config.py
  db.py
  schemas.py
  service.py
  jobs.py
  routes.py
```

Notes:
- `__init__.py` intentionally empty.
- App imports directly from memory submodules.

### 8.3 Separate memory DB and schema bootstrap - Completed

Implemented in `backend/memory/db.py`:
- Dedicated sqlite connection helper for memory DB.
- Idempotent schema bootstrap for:
  - `concepts`
  - `concept_aliases`
  - `concept_edges`
  - `learner_observations`
  - `learner_concept_state`
  - `learner_traits`
  - `memory_versions`
  - `memory_current`
  - `memory_update_jobs`
  - `retrieval_traces`
- Utilities for `list_tables` and `missing_required_tables`.

Boundary achieved:
- Memory tables are not created in `backend/app/db.py`.
- Memory DB resolves to `data/memory.db` at repo root.

### 8.4 Graph simplification (single responder) - Completed

Current graph:
- `START -> memory_loader(optional) -> agent <-> tool_executor -> memory_updater(optional) -> END`

Notes:
- The single responder/tool loop semantics are preserved.
- Memory hooks are additive and do not introduce mode routing.

### 8.5 Memory integration points - Completed

Implemented:
- `memory_loader` is a no-op when memory is disabled or chat scope is unavailable.
- `memory_updater` enqueues memory update jobs when enabled and is a no-op when disabled.
- Failures in both hooks are swallowed/logged to keep chat response path healthy.

### 8.6 Memory HTTP routes ownership - Completed

Implemented:
- Memory endpoints are owned in `backend/memory/routes.py`.
- Memory routes are mounted from the main API router.
- Disabled mode returns `503` with structured `memory_disabled` detail payload.
- Enabled routes serve scoped memory context and memory job listings.
- Authz remains user/subject scoped.

Implemented in commit 6:
- Dedicated worker lifecycle updates job statuses (`pending` -> `running` -> `done`/`failed`) with failure isolation.

### 8.7 Chat route integration - Completed

Implemented state additions in chat initial graph input:
- `user_id`
- `subject_id`
- `memory_context=""`
- `memory_loaded=False`
- `memory_enabled=<runtime flag>`

### 8.8 Seed and local run workflow - Partial

Implemented:
- Schema bootstrap callable (`memory.db.init_db`).

Implemented:
- Dedicated seed command/script: `uv run python -m memory.seed`
- Operational runbook additions for one-shot and long-lived worker runs.

Decision retained:
- No migration from legacy shared-DB memory tables (fresh start).

### 8.9 Tests - Partial

Implemented test coverage:
1. Config/startup gate behavior (on/off/strict conditions).
2. Memory DB isolation checks (memory schema absent from main DB).
3. Memory DB CRUD smoke tests.
4. Graph memory hook behavior (loader enabled/disabled behavior, updater disabled no-op, loop routing preserved).

Commit 6 added coverage:
1. Worker processing integration tests (`tests/test_memory_worker.py`).
2. Failure isolation checks ensuring failed jobs do not block subsequent jobs.

### 8.10 Verification - Partial

Recommended verification commands:

```bash
cd backend
uv run pyright app/
uv run python -m pytest tests/ -n auto
```

Manual checks for local runbook:
- Start app with memory OFF and send one chat request.
- Start app with memory ON and valid `data/memory.db`, run worker, and send one chat request.
- Start app with memory ON and missing DB to verify strict/non-strict behavior.

Focused verification executed through commit 6:
- `uv run python -m pytest tests/test_memory_routes.py tests/test_memory_runtime.py tests/test_health.py -q`
- `uv run python -m pytest tests/test_graph_memory_hooks.py tests/test_chat_stream.py::test_chat_stream_events -q`
- `uv run python -m pytest tests/test_memory_worker.py tests/test_memory_package_imports.py -q`

---

## Expected Outcome at Stage Completion

- Single responder flow with optional memory hooks.
- Memory fully isolated under `backend/memory`.
- Dedicated memory SQLite file at `data/memory.db`.
- Safe runtime gate with default OFF and missing-data fallback.
- Chat remains stable regardless of memory subsystem state.
- Clear operational model for enabling memory in pilot/staging/prod.

---

## Open Decisions

Resolved:
1. Memory route policy: routes stay mounted; disabled state returns `503` + structured reason.
2. Production strict mode default: `MEMORY_STRICT_MODE=true`.
3. Migration strategy: no migration; initialize fresh memory DB.
4. Job execution model: dedicated worker process.
