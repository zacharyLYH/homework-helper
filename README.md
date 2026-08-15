# homework-helper

An AI tutor for homework in subjects with deterministic answers — math, physics, CS, chemistry, economics. It helps students work through the problem in front of them; it is deliberately **not** a general teacher. It does not curate a syllabus or teach a course.

## Why it exists

- AI chatbots are not accountable as teachers, so we stay in the "solve/explain the problem at hand" lane.
- Students need help that is subject-scoped and verifiable, not broad-strokes education.

## Features

- **Homework-alignment gate** — every request is checked against a homework corpus before it reaches the model; out-of-scope requests are rejected up front.
- **Per-subject chats** — subjects don't overlap; each maps to unlimited chats.
- **Image uploads & a drawing board** — take a picture of the assignment or sketch a diagram.
- **Memory system** — a separate database learns a student's strengths, weaknesses, and preferences per subject and injects relevant context into responses.
- **SSE streaming** — tokens appear as they're generated, with markdown rendering.
- **Deliberately deterministic** — checked answers front and center, no drifting into generic tutoring.

## Tech stack

- **Backend**: Python, FastAPI, LangGraph, OpenAI-compatible SDK (Gemini default)
- **Frontend**: React 19, Vite, TypeScript, Tailwind CSS, shadcn/ui
- **Database**: SQLite only (no external DB dependencies)
- **Auth**: email verification code → JWT in an httpOnly cookie
- **Deployment**: Docker Compose on a single machine (nginx frontend + FastAPI backend)

## Getting started

Requires Python 3.10+, [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 18+ and npm.

```bash
git clone <repo-url> && cd homework-helper
./setup.sh
```

That's it — `setup.sh` creates `backend/.env`, installs backend + frontend deps, seeds the databases, pre-downloads the embedding model, and prints the run commands. Re-run it as a dev reset whenever things get into a weird state.

Then add your API key and SMTP credentials to `backend/.env` (see [Configuration](#configuration)). Run the four terminals it prints:

```bash
# terminal 1 — backend (http://127.0.0.1:8000)
cd backend && uv run uvicorn app.main:app --reload

# terminal 2 — frontend (http://localhost:5173)
cd frontend && npm run dev

# terminal 3 — memory worker (optional, for MEMORY_ENABLED=true)
cd backend && uv run python -m memory.jobs --poll-interval 2 --batch-size 20

# terminal 4 — debug page (http://localhost:5174)
cd frontend-debug && npm run dev
```

Or run everything in Docker:

```bash
docker compose up --build
```

## Documentation

| Doc | What it covers |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Core concepts, user flow, alignment gate, LangGraph, data model |
| [`docs/api.md`](docs/api.md) | API reference (generated from the OpenAPI schema) |
| [`backend/memory/README.md`](backend/memory/README.md) | Memory database schema, bootstrapping, worker |

The API reference is generated — regenerate it after endpoint changes:

```bash
cd backend && uv run python scripts/generate_api_docs.py
```

## Project structure

```
backend/          FastAPI app, LangGraph graph, memory package
frontend/         React chat UI (Vite)
frontend-debug/   Admin/debug page (SQL editor, read views)
data/             SQLite databases + seed files
ai-memory-system/ Memory system design docs
docs/             High-level developer + architecture docs
```

## Configuration

All settings live in `backend/.env` (created by `setup.sh`, never overwritten).

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | yes | — | Your OpenRouter API key |
| `OPENROUTER_MODEL` | no | `openrouter/free` | Model to use |
| `JWT_SECRET_KEY` | yes | — | Secret for signing JWT tokens. `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `AES_SECRET_KEY` | yes | — | Secret for encrypting API keys at rest |
| `SMTP_HOST` | no | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | no | `587` | SMTP server port |
| `SMTP_USER` | yes | — | SMTP login username |
| `SMTP_PASSWORD` | yes | — | SMTP login password |
| `SMTP_FROM` | yes | — | Sender address (usually = `SMTP_USER`) |
| `ENVIRONMENT` | no | `dev` | `prod` disables debug endpoints and enables secure cookies |
| `DATABASE_PATH` | no | `data/homework_helper.db` | App SQLite file |
| `DEBUG_DATABASE_PATH` | no | `data/debug.db` | Debug page SQLite file |
| `MEMORY_ENABLED` | no | `false` | Enable LLM memory |
| `MEMORY_DATABASE_PATH` | no | `data/memory.db` | Memory SQLite file |
| `STRUCTURED_LOGGING_PCT` | no | — | % of requests persisted as a full structured trace |
| `HOMEWORK_ALIGNMENT_THRESHOLD` | no | `0.4` | Min cosine similarity for the alignment gate |

### SMTP (send verification codes)

For Gmail: enable 2-Step Verification, create an [app password](https://myaccount.google.com/apppasswords), and use your Gmail address as `SMTP_USER`/`SMTP_FROM` with the app password as `SMTP_PASSWORD`. Other providers: Outlook/Hotmail `smtp-mail.outlook.com:587`, Yahoo `smtp.mail.yahoo.com:587`.

## Development

- Backend: `uv run pyright app/` (type checks), `uv run python -m pytest tests/ -v`
- Frontend: `npx tsc --noEmit`, Playwright (`npm run playwright:test`)
- See [`AGENTS.md`](AGENTS.md) for coding conventions.