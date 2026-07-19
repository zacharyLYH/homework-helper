# homework-helper

this project is specifically for helping users with learn subjects with deterministic answers by doing homework, like math, science, econs, finance, etc. it will not curate a syllabus to teach a user - ai chatbots are not accountable as teachers.

## tech stack

- **backend**: python, fastapi, langgraph, langchain, openai-compatible sdk (gemini by default)
- **frontend**: react 19, vite, typescript, tailwind css, shadcn/ui
- **database**: sqlite
- **auth**: email verification code → JWT in httpOnly cookie
- **deployment**: docker, single machine, nginx frontend + fastapi backend in same compose file

## core concepts

- **subject**: the global divisor. subjects do not overlap. 1 subject maps to infinite chats.
- **topic**: groups concepts within a subject. topics may overlap with other subjects' topics, in which case we fall back to the subject-level md file.
- **concept**: the finest granularity. concepts may overlap with other subjects' concepts, in which case we fall back to the topic-level md file, then subject-level.
- **memory file**: a markdown file with yaml frontmatter. one file per subject, topic, and concept. captures strengths, weaknesses, and observations.
- **memory index**: a single yaml file listing all known subject→topic→concept paths. used by the llm to find the right memory file before responding. if no matching concept exists, the ai creates a new concept file and adds it to the index.
- **version**: every memory file update creates a new immutable version row. we never overwrite or delete memory files. this lets us build an evolution graph for evaluation.
- **mode**: per chat, set at conversation start. two modes: guide (ai walks the user through the problem) and just-solve (ai gives the answer with explanation). cannot be toggled mid-conversation.
- **api key**: user-provided. stored in sqlite. if missing, the ui blocks the user from proceeding. even if they bypass the ui, the backend will reject requests due to missing key.
- **openrouter api key**: optional. used for cheap/free model calls for background tasks like chat title generation. stored in sqlite alongside the primary api key. if missing, fall back to heuristic titles (e.g., first 30 chars of first message).

## user flow

1. user opens the app. if no api key is stored, the ui forces them to enter one before proceeding. they may optionally provide an openrouter api key for cheap background tasks.
2. user creates a new subject (e.g., "ap calculus bc").
3. user starts a new chat under that subject. at chat creation, they choose guide or just-solve mode.
4. user asks questions by typing or taking a picture (base64 image upload). no assignment file uploads.
5. backend routes the message through the langgraph graph.
6. before the first reply in a turn, the background ai loads the relevant memory files (subject → topic → concept) based on the memory index.
7. the ai responds according to the chosen mode.
8. after every turn, the background ai decides whether to update any memory file. updates are selective — it only writes when it genuinely detects a strength or weakness. the ai must be conservative; brevity in memory files is a feature, not a bug.
9. if a concept does not yet exist, the ai creates a new concept md file and adds it to the memory index.
10. users can return to previous conversations at any time. chat histories are persisted in sqlite.

## data model

### users
- id
- email (unique)
- created_at

### verification_codes
- id
- email
- code (6-digit)
- expires_at
- created_at

### subjects
- id
- user_id (foreign key to users)
- name
- created_at

### chats
- id
- subject_id (foreign key to subjects)
- user_id (foreign key to users)
- mode: enum ("guide", "just-solve")
- title (ai-generated)
- created_at
- updated_at

### messages
- id
- chat_id (foreign key to chats)
- role: enum ("user", "assistant", "system")
- content
- image_base64 (compressed and nullable)
- image_media_type (nullable if image_base64=null)
- metadata: json (tool calls, token usage, node routing info)
- created_at

### memory_files
- id
- user_id (foreign key to users)
- subject_id (nullable, foreign key to subjects)
- type (subject/topic/concept)
- path: string (e.g., "ap-calculus-bc/derivatives/chain-rule")
- created_at
- updated_at

### memory_versions
- id
- memory_file_id (foreign key to memory_files)
- version: integer
- content: text (snapshot of the full file at this version)
- change_summary: text (brief note on what changed)
- created_at

## memory file format (yaml frontmatter + markdown body)

```yaml
---
path: ap-calculus-bc/derivatives/chain-rule
type: concept
strengths:
  - understands basic chain rule
weaknesses:
  - forgets to differentiate inner function first
  - forgets some other thing...
last_observed: 2026-07-15
---
# Chain Rule

the chain rule is used when differentiating composite functions...
```

- `type`: one of "subject", "topic", "concept"
- `strengths`: list of observed strengths
- `weaknesses`: list of observed weaknesses
- `last_observed`: date of most recent interaction touching this concept
- body: free-form markdown where the ai can note examples, common mistakes, or teaching strategies

## memory index format (yaml)

```yaml
subjects:
  - name: ap-calculus-bc
    topics:
      - name: derivatives
        concepts:
          - name: chain-rule
            path: ap-calculus-bc/derivatives/chain-rule
          - name: product-rule
            path: ap-calculus-bc/derivatives/product-rule
```

the ai loads this index into context, picks the closest matching path, loads that memory file, and uses it to inform its response.

## langgraph architecture

### state

```python
class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    category: str
    mode: str  # "guide" | "just-solve"
    memory_context: str  # loaded memory files injected here
    subject_id: str
    user_id: str
```

### nodes

1. **router**: classifies the latest message and routes to the appropriate subject/expert node. also responsible for triggering memory load.
2. **memory_loader** (new): reads the memory index, finds relevant files, injects them into `memory_context`. runs before the first reply of a turn.
3. **guide_mode_responder**: walks the user through the problem step by step. does not give the final answer up front.
4. **just_solve_mode_responder**: solves the problem directly with a clear explanation.
5. **memory_updater** (new): after every response, decides whether any memory file needs updating. if yes, creates a new version row and updates the index if a new concept was created. must be highly selective.
6. **tool_executor**: runs any tools the model calls (calculator, etc.).

### edges

- START → router
- router → memory_loader (always, first turn)
- memory_loader → mode_responder
- mode_responder → tool_executor (if tool calls)
- tool_executor → memory_updater
- mode_responder → memory_updater (if no tool calls)
- memory_updater → END

### hooks (contract for memory integration)

two extension points in the graph allow memory nodes to be registered without modifying the core graph structure:

- `load_memory_hook(state: GraphState) → dict[str, Any]`: returns a dict to merge into state, typically `{"memory_context": "..."}`.
- `update_memory_hook(state: GraphState) → dict[str, Any]`: returns a dict to merge into state, typically recording that a memory update occurred.

## backend api contract

### auth
- all endpoints (except health and auth) require a valid JWT cookie (`jwt_token`) or `Authorization: Bearer <jwt>` header.
- flow: user enters email → backend checks if user exists → sends 6-digit verification code via email → user enters code → backend sets httpOnly cookie with JWT (24h expiry) and returns it in response body.
- jwt contains: `sub` (user id), `email`, `iat`, `exp`.
- backend validates JWT on every protected request via FastAPI dependency. cookie is sent automatically by the browser on same-origin requests.

### endpoints

**auth**
- `POST /api/auth/request-code` — send verification code to email (requires registered email)
- `POST /api/auth/verify` — verify code, set httpOnly cookie, return JWT + user info
- `GET /api/auth/me` — get current user from JWT cookie (returns `{id, email}`)

**debug** (public when `ENVIRONMENT != "prod"`)
- `GET /api/debug/users` — list all users
- `GET /api/debug/messages` — list recent messages
- `GET /api/debug/chats` — list all chats

**subjects**
- `POST /api/subjects` — create subject
- `GET /api/subjects` — list subjects
- `DELETE /api/subjects/{id}` — delete subject (cascade or restrict if chats exist)

**chats**
- `POST /api/subjects/{subject_id}/chats` — create chat (requires mode: guide | just-solve)
- `GET /api/subjects/{subject_id}/chats` — list chats for subject
- `GET /api/chats/{chat_id}` — get chat details + message history
- `DELETE /api/chats/{chat_id}` — delete chat

**chat execution**
- `POST /api/chat` — send a message (non-streaming)
  - request: `{ message, thread_id?, image?, image_media_type?, chat_id? }`
  - response: `{ reply, thread_id, run: { node, token_usage, tool_calls } }`
- `POST /api/chat/stream` — send a message (SSE streaming)
  - request: same as above
  - response: `text/event-stream` with events:
    - `data: {"type":"token","content":"..."}`
    - `data: {"type":"done","thread_id":"..."}`
    - `data: {"type":"error","content":"..."}`
  - note: `thread_id` is the langgraph checkpointer thread id. `chat_id` ties the conversation to a stored chat.

**memory**
- `GET /api/memory/index` — get memory index for current user
- `POST /api/memory/files` — create memory file (mostly for ai, but exposed for evaluation)
- `GET /api/memory/files/{id}` — get memory file + version history
- `GET /api/memory/files/{id}/versions/{version}` — get specific version

**evaluation**
- `GET /api/eval/conversations` — list all conversations with metadata
- `GET /api/eval/conversations/{chat_id}` — full conversation log + memory updates
- `GET /api/eval/memory/{memory_file_id}/evolution` — version diff timeline

**tools**
- `GET /api/tools` — list available tools

**health**
- `GET /health` — service health + model info

## frontend ui

### login
- email input → request verification code → code input → verify → redirect to chat.
- JWT is stored as an httpOnly cookie, persists across browser refreshes automatically.

### chat interface
- SSE streaming responses (tokens appear as they are generated).
- markdown rendering for assistant responses.
- clean, minimal UI built with tailwind css and shadcn/ui components.
- logout button in header.

### debug page
- accessible via bug icon in chat header.
- shows all users, chats, and recent messages from the database.
- only accessible in non-production environments.

## docker

- single `docker-compose.yml` with two services: `backend` and `frontend`.
- backend exposes port 8000 (internal, not directly accessed).
- frontend serves via nginx on port 80, proxying `/api/*` requests to the backend.
- cookies work because both frontend and backend are served from the same origin.
- sqlite file mounted as a volume so data persists across container restarts.
- environment variables for openrouter/gemini base url

## non-functional requirements

- **homework-only policy**: all system prompts must instruct the model to reject non-homework questions. the model should decline questions that are general knowledge, creative writing, open-ended research, or unrelated to a user's declared subject. it should redirect the user back to their homework.
- **sqlite only**: no external database dependencies. all data (users, subjects, chats, messages, memory files, versions, index) lives in sqlite.
- **image handling**: images are base64-encoded and passed directly to the model. no ocr pre-processing. assumes a vision-capable model (gemini by default).
- **memory selectivity**: the ai must not update memory files on every turn. it should only write when it detects a meaningful signal (e.g., user consistently making a specific mistake, or demonstrating clear mastery). memory files should be concise.
- **no deletion**: memory files are never deleted. only new versions are appended. users can delete chats and subjects, but memory persists.
- **conversation persistence**: users can leave and return. chat state is recovered from sqlite + langgraph checkpointer.

## open questions

- exact prompt engineering for the background ai's selective update logic
- evaluation page design and metrics

## Developer docs

### 1. Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (package manager)
- Node.js 18+ and npm
- An OpenRouter API key (free tier works)

### 2. First-time setup

```bash
git clone <repo-url> && cd homework-helper
./setup.sh
```

This creates virtual environments, installs backend + frontend dependencies, and generates `backend/.env`.

Then add your API key and SMTP credentials:

```bash
# edit backend/.env
OPENROUTER_API_KEY=sk-or-v1-...
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=you@gmail.com
```

### 3. Run locally

Two terminals:

```bash
# terminal 1 — backend (http://127.0.0.1:8000)
cd backend && uv run uvicorn app.main:app --reload

# terminal 2 — frontend (http://localhost:5173)
cd frontend && npm run dev
```

Open http://localhost:5173, enter your email, and start chatting. The Vite dev server proxies `/api` requests to the backend.

### 5. Database

SQLite file at `data/homework_helper.db`. Created automatically on first backend start.

Tables: `users`, `subjects`, `chats`, `messages`, `verification_codes`.

Query it directly:

```bash
sqlite3 data/homework_helper.db ".tables"
sqlite3 data/homework_helper.db "SELECT * FROM messages;"
```

In Docker, the DB is bind-mounted from `data/` so it persists across container restarts.

### 6. Logging

Logs go to stdout with format:

```
2026-07-18 10:54:01 [INFO] app.routes.chat: Chat request: thread_id=..., message_length=14
```

Configure level via `LOG_LEVEL` env var (default: `INFO`). Set to `DEBUG` for verbose output.

### 7. Docker

```bash
docker compose up --build
```

- Frontend: http://localhost:80 (nginx, proxies /api to backend)
- Backend: http://localhost:8000 (internal)

The SQLite database is stored in `data/` on the host (bind mount), not a Docker volume.

To stop and remove containers:

```bash
docker compose down
```

### 8. Type checking

```bash
cd backend && uv run pyright app/
cd frontend && npx tsc --noEmit
```

Zero errors expected. Run this before committing.

### 9. Environment variables

Set in `backend/.env` (copied from `.env.example` by setup.sh):

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | yes | — | Your OpenRouter API key |
| `OPENROUTER_MODEL` | no | `openrouter/free` | Model to use |
| `JWT_SECRET_KEY` | yes | — | Secret key for signing JWT tokens. Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SMTP_HOST` | no | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | no | `587` | SMTP server port |
| `SMTP_USER` | yes | — | SMTP login username (your email address) |
| `SMTP_PASSWORD` | yes | — | SMTP login password (see below) |
| `SMTP_FROM` | yes | — | Sender email address (usually same as `SMTP_USER`) |
| `LOG_LEVEL` | no | `INFO` | Logging level |
| `ENVIRONMENT` | no | `dev` | Set to `prod` to disable debug endpoints and enable secure cookie |
| `DATABASE_PATH` | no | `data/homework_helper.db` | SQLite file path |
| `BACKEND_URL` | no | `http://127.0.0.1:8000` | Frontend→backend URL (set in Docker) |

#### Obtaining SMTP credentials

**Gmail (recommended for dev):**
1. Enable 2-Step Verification on your Google Account
2. Go to https://myaccount.google.com/apppasswords
3. Generate an app password for "Mail"
4. Use your Gmail address as `SMTP_USER` and `SMTP_FROM`
5. Use the 16-character app password as `SMTP_PASSWORD`

**Other providers:**
- Outlook/Hotmail: `SMTP_HOST=smtp-mail.outlook.com`, `SMTP_PORT=587`
- Yahoo: `SMTP_HOST=smtp.mail.yahoo.com`, `SMTP_PORT=587`

**Note:** `SMTP_USER` and `SMTP_PASSWORD` are the actual login credentials. `SMTP_FROM` is the address recipients see — most providers only allow sending from your own address or verified aliases.

