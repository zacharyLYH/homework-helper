# Commit Strategy (Reworked v2)

Direction changed:
- Remove guide vs just-solve mode split.
- Make memory use its own SQLite file (separate from main app DB).
- Make memory a standalone backend package under `backend/memory`.
- Add env-gated enablement; memory defaults to OFF when memory DB/data is missing.

This replaces the previous commit 4/5 plan that depended on mode routing.

---

## Commit contract (applies to every commit)

Each commit must satisfy all three requirements:

1. Clear scope implemented
- Exactly one primary concern per commit.
- No opportunistic refactors unrelated to that concern.

2. That scope is testable and tested
- Add or update focused tests proving the changed behavior.
- Keep tests for unchanged behavior green.

3. Entire app still runnable with memory OFF and ON
- OFF profile: `MEMORY_ENABLED=false`.
- ON profile: `MEMORY_ENABLED=true` with valid `data/memory.db` schema.

If a commit cannot satisfy the ON profile yet (because enabling logic is not introduced), that commit must include a temporary ON acceptance note and the earliest commit that makes ON runnable.

---

## Commit sequence by work item (strict)

### Commit 1: Runtime config and memory capability check (done)

Primary scope:
- Add `MEMORY_ENABLED` and `MEMORY_STRICT_MODE` config wiring.
- Use fixed memory DB path at `data/memory.db` (no configurable path in `.env`).
- Implement canonical memory capability check used by app startup/runtime gating.

Out of scope:
- No memory DB schema creation.
- No graph behavior changes.
- No route ownership moves.

Tests in this commit:
- Unit tests for config defaults and parsing.
- Startup/capability tests:
  - memory off -> disabled
  - memory on + missing DB/schema + strict true -> startup failure
  - memory on + missing DB/schema + strict false -> auto-disable

Run checks after commit:
- App runs with memory OFF.
- App runs with memory ON only when strict allows fallback or DB exists.

Acceptance gate:
- Memory capability state is explicit and can be consumed by all later commits.

---

### Commit 2: Standalone package boundary under backend/memory (done)

Primary scope:
- Create package skeleton and move memory internals under `backend/memory`.
- Keep public interfaces stable for callers.

Out of scope:
- No persistence split yet.
- No graph topology change yet.

Tests in this commit:
- Import-level tests for package entrypoints.
- Regression tests that existing app startup/chat paths are unaffected when memory is disabled.

Run checks after commit:
- App runs with memory OFF.
- App runs with memory ON with current gating behavior from commit 1.

Acceptance gate:
- No memory business logic remains scattered across `backend/app/*` internals.

---

### Commit 3: Dedicated memory SQLite file and schema bootstrap (done)

Primary scope:
- Implement separate connector and schema bootstrap in `backend/memory/db.py`.
- Ensure memory tables are no longer initialized in main app DB.
- Decision locked: no migration from legacy shared DB memory tables.

Out of scope:
- No graph flow changes.
- No route behavior policy changes.

Tests in this commit:
- DB isolation tests:
  - memory schema appears in memory DB file
  - memory schema absent from main DB
- CRUD smoke tests against memory DB.

Run checks after commit:
- App runs with memory OFF.
- App runs with memory ON and valid memory DB path/schema.

Acceptance gate:
- Memory persistence is physically and operationally decoupled from main DB.

---

### Commit 4: Graph memory hooks + state wiring on current single loop (done)

Primary scope:
- Keep the existing single `agent <-> tool_executor` loop.
- Add optional `memory_loader` and `memory_updater` hooks around that loop.
- GraphState reduced to memory-relevant fields only.

Implemented:
- Graph now runs `START -> memory_loader -> agent <-> tool_executor -> memory_updater -> END`.
- Chat route now passes memory fields into initial graph state: `user_id`, `subject_id`, `memory_context`, `memory_loaded`, `memory_enabled`.
- Memory service now provides `load_memory_context` and `enqueue_memory_update` for hook integration.

Out of scope:
- No route contract change.
- No worker process yet.

Tests in this commit:
- Graph wiring tests (single loop preserved).
- Memory loader invoked only when capability is enabled.
- Memory updater is no-op when memory disabled.

Executed:
- `tests/test_graph_memory_hooks.py`
- `tests/test_chat_stream.py::test_chat_stream_events`
- `tests/test_health.py`
- `tests/test_memory_runtime.py`

Run checks after commit:
- App runs with memory OFF and chat still functional.
- App runs with memory ON and chat still functional with memory context injection.

Current verification status:
- Focused commit 4 test suite passes.
- Full manual OFF/ON runbook verification is still tracked for final verification bundle.

Acceptance gate:
- Memory hooks are integrated without changing existing chat/tool loop semantics.

---

### Commit 5: Memory API contract and disabled policy (done)

Primary scope:
- Move/own memory endpoints in `backend/memory/routes.py`.
- Keep memory routes mounted always.
- Enforce disabled contract: `503 Service Unavailable` + structured `memory_disabled` payload.

Implemented:
- Memory endpoints are owned by `backend/memory/routes.py`.
- Memory router is mounted in `backend/app/routes/__init__.py` and available in both OFF/ON profiles.
- Disabled contract is enforced with structured payload in `HTTPException(detail=...)`.
- Enabled routes currently provide:
  - `GET /api/memory/subjects/{subject_id}/context`
  - `GET /api/memory/subjects/{subject_id}/jobs`
- Subject ownership authz is enforced for memory endpoints.

Out of scope:
- No worker-process orchestration yet.

Tests in this commit:
- Route tests:
  - disabled mode returns 503 contract
  - enabled mode returns real data paths
  - authz remains user-scoped

Executed:
- `tests/test_memory_routes.py`
- Regression checks: `tests/test_memory_runtime.py`, `tests/test_health.py`, `tests/test_graph_memory_hooks.py`, `tests/test_chat_stream.py::test_chat_stream_events`

Run checks after commit:
- App runs with memory OFF and returns 503 on memory endpoints.
- App runs with memory ON and memory endpoints function normally.

Current verification status:
- Focused commit 5 route and regression suites pass.
- Full manual OFF/ON runbook verification remains tracked for final verification bundle.

Acceptance gate:
- API clients can reliably distinguish disabled vs broken/missing routes.

---

### Commit 6: Dedicated memory worker + final verification bundle (done)

Primary scope:
- Add dedicated worker process for memory job execution.
- Add memory seed scripts and runbook commands (DB init bootstrap already shipped in commit 3).
- Finalize end-to-end verification coverage.

Implemented:
- `backend/memory/jobs.py` now provides a dedicated worker loop and one-shot mode (`--once`) that claims `pending` jobs, processes them, and marks `done`/`failed` with failure isolation.
- `backend/memory/seed.py` and `data/memory-seed.sql` provide deterministic local seed workflow.
- `docker-compose.yml` now includes a `memory-worker` service for async memory job execution in containerized runs.
- Worker integration tests were added and regression tests for chat/runtime/memory routes were re-run.

Out of scope:
- No additional architecture pivots.

Tests in this commit:
- Worker integration tests:
  - jobs are picked and processed
  - worker failures are isolated from chat path
- Full regression suite for OFF and ON profiles.

Executed:
- `uv run pyright memory/`
- `uv run python -m pytest tests/test_memory_worker.py tests/test_memory_routes.py tests/test_memory_runtime.py tests/test_graph_memory_hooks.py tests/test_chat_stream.py::test_chat_stream_events tests/test_health.py tests/test_memory_package_imports.py -q`

Run checks after commit:
- App runs with memory OFF end-to-end.
- App runs with memory ON end-to-end with worker processing jobs.

Acceptance gate:
- Architecture is production-runnable with clear operations for both profiles.

---

## Execution checklist per commit (must copy into PR description)

For each commit PR, include:

1. Scope statement
- "This commit changes only: ..."

2. Tests executed
- List exact test files or markers run.
- Include pass/fail result.

3. App run verification
- OFF profile: startup + one chat request.
- ON profile: startup + one chat request + one memory endpoint check.

4. Known limitations
- Explicitly state what is intentionally deferred to next commit.

---

## Mapping summary

| Commit | Theme | Risk | Why order matters |
|---|---|---|---|
| 1 | Feature flag + auto-disable | Low | Defines safe default behavior first |
| 2 | Package isolation | Medium | Creates clean boundaries before data move |
| 3 | Dedicated memory DB | High | Core architecture change lands after scaffolding |
| 4 | Graph memory hooks wiring | Medium | Adds memory behavior without destabilizing current loop |
| 5 | Route ownership + gating | Low | Finalizes operational API behavior |
| 6 | Worker + seed/tests/verification | Medium | Completes async processing and operational readiness |

## PR slicing recommendation

- PR 1: Commits 1-3 (platform and data architecture).
- PR 2: Commits 4-6 (runtime behavior and integration).

This split keeps high-risk persistence changes reviewable before graph/runtime rewiring.