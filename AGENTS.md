# What is this file?

This file tells ai coding agents about the conventions and expected practices when interacting with this code base.

# When to make sure of information in this file?

Use it EVERYTIME you write any code.

# What is this app?

homework-helper is an AI tutor that helps students work through homework problems in subjects with deterministic answers (math, physics, CS, chemistry, economics, etc.). It is deliberately NOT a general teacher: it does not curate a syllabus or teach a course. It helps with the homework in front of the student.

Why it exists:
- AI chatbots are not accountable as teachers, so we stay in the "solve/explain the problem at hand" lane.
- Students need help that is subject-scoped and verifiable, not broad-strokes education.

Key behaviors:
- A **homework-alignment gate** rejects out-of-scope requests (anything not homework) before they hit the model.
- Per-subject chats, image uploads of assignments, and a drawing/whiteboard for diagrams.
- A **memory system** (separate SQLite DB) that learns a student's strengths/weaknesses per subject over time and injects relevant context into responses.

Ethos (use as a guide for small judgement calls):
- Prioritize helping the student solve the current problem correctly over lecturing broadly.
- Keep deterministic, checked answers front and center; do not drift into generic tutoring.
- The homework-alignment gate is strict by design — when in doubt, keep the model response in-scope.
- Memory context is a preference/observation aid, never treated as ground truth about the student.

# Overall rules that apply to every scenario

The following list of rules is true no matter what kind of code you're writing, frontend, backend, tests, or even deployment scripts.

1. Minimal code change that satisfies the user's ask. If the user's precise ask is unclear, you MUST clarify. Optionally, get the user to explicitly sign off on the change set if the change required is medium sized and above. 
2. Do not speculate what the user wants. Just ask.
3. KISS in general. Simple architecture, simple code patterns, minimal external dependencies. 
4. When discussing with the user, like in a code deep dive for example, you should always be concise with your answers. Wall of text is not the right way to format responses. Responses to technical discussion should be short, concise, and in bullet point form where required. You should SACRIFICE grammatical correctness for concision. 
5. This is an AI app. The layout and behavior of most components is well understood and we don't intend to greatly deviate from established UX and practices. YOU SHOULD ALWAYS USE COMMON SENSE AND MAKE SMALL JUDGEMENT CALLS.
6. Keep the docs current. Whenever you add, remove, or change an API route (or its request/response schemas), regenerate `docs/api.md` with `cd backend && uv run python scripts/generate_api_docs.py`. If a change touches setup/behavior surface, update the README (or its `docs/` links) as part of the change.

# Coding standards in general

This is how you know you've written good code by my definition.

1. Your code is modularized-as-needed. The signs: your changes are not a thin modules, your changes are only in a module IFF its theoretically a medium likelihood replaceable component (as long as contract is kept the same).
2. Your code changes come with some form of test. Ideally its a e2e test and or UAT test but if not ameanable to those higher level testing then at least a unit test. Happy, sad, and common edge cases need to be tested.
3. There are industry established coding standards for the technologies we're using. We should always try to align as a default, and deviate only if the user explicitly deviates. But, it should then be documented why we're not following best practices. 

> Note: You shouldn't be eagerly write tests until the user has confirmed that the code looks correct enough to start testing. Otherwise you might be wasting the user's time and tokens if the user is not happy with the code changes yet.

# Per technology specific standards

## Python backend
1. Most code Python should be typed. Only where it is very cumbersome to create/maintain a type are you allowed to use `Any` type or ask to ignore type checking by the LSP.
2. On code change complete, run `uv run pyright app/` to make sure no LSP issues.
3. To  In VSCode do `Cmd + ,`. Search for `python.analysis.typeCheckingMode`. Change from `Off` to `Standard`. This activates the LSP.
4. Tests should be run after every change to certify no regressions. New tests should also be added to assert new behavior if there is a backend change `python -m pytest tests/ -v`.

## React frontend
1. Sparingly use advanced hooks, only if performance of some component is critical should you use advanced hooks. Otherwise stick to simple ones like `useState()` and `useEffect()`
2. A loaded prop definition is hard to work with and naturally scales the lines of code in some module. In general we try to minimize the number of props per component.
3. Make use of polished shadcn UI components where possible. The user might not make it explicit of the UI they want, but you should use common sense to try to fit shadcn UI components where it makes sense. Inventing your own UI components should only happen if the user has expressed unhappiness with existing UIs and explicitly describes how they want a component to look.
4. Frontend tests are Playwright-based, run from `frontend/`:
   - `npm run playwright:test` — full suite
   - `npm run playwright:behavioral` — interaction/UX flows (mocked backend via `tests/helpers/stream.ts`)
   - `npm run playwright:performance` — web vitals + interaction perf (see `tests/performance/vitals.ts`)
   - `npm run playwright:visual` — responsive grid screenshots (dark/light × phone/tablet/desktop)
   - `npm run playwright:update` — regenerate visual snapshots
   - `npx playwright test --ui` — interactive test runner
   Tests spin up a preview server automatically (`npm run preview --port 4173`). Visual baselines live in `frontend/tests/visual/responsive.spec.ts-snapshots/`.

## Sqlite DB
1. On every database change like adding a new column, make sure to update the seed files:
   - `data/purge-and-seed.sql` — mini representation of the main app DB data-backed features (`users`, `subjects`, `chats`, `messages`, `verification_codes`).
   - `data/memory-seed.sql` — mini representation of the standalone memory DB (`concepts`, `concept_edges`, `learner_observations`, `learner_traits`, `memory_summary`, `memory_update_jobs`, `retrieval_traces`).
   If a new table/column/feature has seedable data, mirror it in the matching seed file.
2. The memory DB schema lives in `backend/memory/db.py`; the app DB schema in `backend/app/db.py`. Seed files are only applied via `python -m memory.seed` (memory) and `sqlite3 ... ".read data/purge-and-seed.sql"` (app) — there is no `seed_db` function on `app.db`, do not reference one.
