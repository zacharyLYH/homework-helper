# Stage 06: Backend - Test Infrastructure (Mockers + Harness)

**Sequence: 6 of 7**
**Scope: `backend/tests/` (new directory), `backend/pyproject.toml`**
**Goal: Create test framework, mockers for external services, reusable test harness**

---

## Why This Stage Sixth

Before writing actual UAT tests, we need infrastructure: pytest configuration, a test database fixture, mockers for LLM and email calls, and a harness that makes each test declarative. Building this first means every subsequent test is a one-liner setup.

---

## Guidelines (STRICT)

1. **DO NOT mock internal functions.** Mock at the boundary: HTTP responses from LLM API, SMTP send calls.
2. **DO NOT use the production database.** Every test gets its own temporary `.db` file.
3. **Tests must be independent.** No test should depend on another test's state.
4. **Verify: `cd backend && python -m pytest tests/ -v`**

---

## Work Items

### 6.1: Add pytest and test dependencies

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]
```

Then run:
```bash
cd /Users/zac/Desktop/homework-helper/backend
uv pip install -e ".[dev]"
```

### 6.2: Create test directory structure

```
backend/tests/
├── __init__.py
├── conftest.py              # Shared fixtures and harness
├── mockers.py               # LLM and email mockers
├── seed.py                  # SQL seed helper
├── test_auth.py             # Auth endpoint tests
├── test_subjects_chats.py   # Subject/chat CRUD tests
├── test_chat_stream.py      # Chat streaming tests
├── test_health.py           # Health endpoint tests
└── test_debug.py            # Debug endpoint tests
```

### 6.3: Create `conftest.py` — the test harness

This is the most important file. It provides:

1. **A temporary database** for each test
2. **A FastAPI test client** using `httpx.AsyncClient`
3. **A seeded database** with known data
4. **Auth helper** to get a JWT token for any user

```python
import pytest
import pytest_asyncio
import tempfile
import os
from pathlib import Path
from httpx import AsyncClient, ASGITransport

# Override database path BEFORE importing app
@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Create a fresh test database for each test."""
    db_path = str(tmp_path / "test.db")
    os.environ["DATABASE_PATH"] = db_path
    
    # Re-import settings to pick up new env
    import importlib
    import app.config
    importlib.reload(app.config)
    
    # Initialize database
    import app.db
    importlib.reload(app.db)
    app.db.DB_PATH = Path(db_path)
    app.db.init_db()
    
    yield db_path
    
    # Cleanup
    os.environ.pop("DATABASE_PATH", None)


@pytest_asyncio.fixture
async def client(setup_test_db):
    """Async test client for the FastAPI app."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def seed(setup_test_db):
    """Seed the test database with known data."""
    from app.db import get_conn
    
    def _seed(sql_file: str = None, *, users=None, subjects=None, chats=None):
        if sql_file:
            with get_conn() as conn:
                conn.executescript(open(sql_file).read())
        # Programmatic seeding for flexibility
        if users:
            with get_conn() as conn:
                for email in users:
                    conn.execute("INSERT INTO users (email) VALUES (?)", (email,))
        if subjects:
            with get_conn() as conn:
                for user_id, name in subjects:
                    conn.execute("INSERT INTO subjects (user_id, name) VALUES (?, ?)", (user_id, name))
        if chats:
            with get_conn() as conn:
                for subject_id, user_id, mode, title in chats:
                    conn.execute(
                        "INSERT INTO chats (subject_id, user_id, mode, title) VALUES (?, ?, ?, ?)",
                        (subject_id, user_id, mode, title),
                    )
    return _seed


@pytest.fixture
def auth_token(setup_test_db):
    """Get a valid JWT token for a test user."""
    from app.db import get_conn
    from app.auth import create_access_token
    from app.schemas import User
    from datetime import datetime, timezone
    
    def _get_token(email: str = "alice@school.edu") -> str:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not row:
                conn.execute("INSERT INTO users (email) VALUES (?)", (email,))
                row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            user = User(id=row["id"], email=row["email"], created_at=row["created_at"])
            return create_access_token(user)
    return _get_token
```

### 6.4: Create `mockers.py` — LLM and email mockers

```python
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Generator
from langchain_core.messages import AIMessage


class MockLLMResponse:
    """Mock LLM response that yields configurable tokens."""
    
    def __init__(self, content: str = "Hello! How can I help?", model: str = "test-model"):
        self.content = content
        self.model = model
        self.response_metadata = {"model_name": model}
        self.usage_metadata = {
            "input_tokens": 10,
            "output_tokens": len(content.split()),
            "total_tokens": 10 + len(content.split()),
        }
        self.tool_calls = []


def mock_cycling_invoke(responses: list[MockLLMResponse] = None):
    """Return a patcher that replaces _cycling_invoke with predictable responses."""
    if responses is None:
        responses = [MockLLMResponse()]
    
    call_count = 0
    
    def _mock_invoke(messages, bind_tools=None):
        nonlocal call_count
        resp = responses[call_count % len(responses)]
        call_count += 1
        return resp, resp.model
    
    return patch("app.graph._cycling_invoke", side_effect=_mock_invoke)


def mock_title_llm(title: str = "Test Chat Title"):
    """Mock the title generation LLM."""
    mock_response = MagicMock()
    mock_response.content = title
    
    async def _mock_astream(prompt):
        yield mock_response
    
    return patch("app.routes.chat.title_llm")


def mock_email_send():
    """Mock email sending. Returns True (success)."""
    return patch("app.routes.auth.send_verification_email", return_value=True)


def mock_email_send_failure():
    """Mock email sending failure."""
    return patch("app.routes.auth.send_verification_email", return_value=False)
```

### 6.5: Create `seed.py` — SQL seed helper

```python
"""SQL seed scenarios for UAT tests."""

INITIAL_SEED = """
INSERT INTO users (id, email, created_at) VALUES
    (1, 'alice@school.edu', '2025-01-01T00:00:00'),
    (2, 'bob@school.edu', '2025-01-01T00:00:00');

INSERT INTO subjects (id, user_id, name, created_at) VALUES
    (1, 1, 'Math', '2025-01-01T00:00:00'),
    (2, 1, 'Physics', '2025-01-01T00:00:00'),
    (3, 2, 'Chemistry', '2025-01-01T00:00:00');

INSERT INTO chats (id, subject_id, user_id, mode, title, total_tokens, input_tokens, output_tokens, created_at, updated_at) VALUES
    (1, 1, 1, 'guide', 'Algebra Help', 150, 80, 70, '2025-01-01T00:00:00', '2025-01-01T00:00:00'),
    (2, 1, 1, 'just-solve', 'Calculus Q', 0, 0, 0, '2025-01-02T00:00:00', '2025-01-02T00:00:00');

INSERT INTO messages (id, chat_id, role, content, token_count, created_at) VALUES
    (1, 1, 'user', 'What is 2+2?', 5, '2025-01-01T00:00:00'),
    (2, 1, 'assistant', 'The answer is 4.', 10, '2025-01-01T00:00:01');
"""
```

### 6.6: Configure pytest

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### 6.7: Verify test infrastructure

Run:
```bash
cd /Users/zac/Desktop/homework-helper/backend
python -m pytest tests/ -v --collect-only
```

This should discover 0 tests (we haven't written any yet) but confirm the infrastructure loads without errors.

Also verify mockers work:
```bash
python -c "
from tests.mockers import MockLLMResponse, mock_cycling_invoke, mock_title_llm, mock_email_send
print('Mockers import OK')
"
```

---

## Expected Outcome

- pytest configured and installable
- Test directory with conftest, mockers, seed data
- Each test gets isolated DB, test client, auth tokens
- Mockers for LLM, title generation, and email sending
- Zero tests written yet (that's stage 07)
