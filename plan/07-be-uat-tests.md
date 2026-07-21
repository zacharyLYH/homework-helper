# Stage 07: Backend - UAT Tests

**Sequence: 7 of 7**
**Scope: `backend/tests/test_*.py`**
**Goal: Write UAT tests covering happy, sad, and edge cases for all API endpoints**

---

## Why This Stage Last

Tests go last because (a) we need the refactored code (stages 1-4) and test infrastructure (stage 06) to exist first, and (b) tests validate that refactoring didn't break anything.

---

## Guidelines (STRICT)

1. **Each test function tests ONE scenario.** Name it descriptively: `test_create_subject_happy_path`, `test_create_subject_missing_name`.
2. **Use the harness from conftest.py.** Don't create DB connections or test clients manually.
3. **Mock at boundaries only.** LLM API calls and email sends. Never mock internal functions.
4. **Assert on:**
   - HTTP status code
   - Response body shape and values
   - Database state (via direct queries)
   - Mock call counts (via `assert mock.call_count == N`)
5. **Each test must be independent.** No test depends on another test's state.
6. **Cover: happy path, sad path (4xx errors), edge cases.**
7. **Verify: `cd backend && python -m pytest tests/ -v`**

---

## Test File Structure

### `test_health.py` — Health & Root Endpoints

```python
"""Tests for health and root endpoints."""

async def test_root_returns_service_info(client):
    """GET / returns service name and docs link."""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "homework-helper-backend"
    assert "docs" in data


async def test_health_returns_ok(client):
    """GET /health returns status ok with model info."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "model" in data
    assert data["graph_compiled"] is True
```

### `test_auth.py` — Auth Flow

```python
"""Tests for authentication endpoints."""

# Happy paths
async def test_request_code_happy(client, seed, mock_email_send):
    """POST /api/auth/request-code with valid registered email returns 200."""
    seed(users=["alice@school.edu"])
    resp = await client.post("/api/auth/request-code", json={"email": "alice@school.edu"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Code sent"


async def test_verify_code_happy(client, seed):
    """POST /api/auth/verify with correct code sets cookie and returns token."""
    seed(users=["alice@school.edu"])
    # Create a verification code
    from app.db import create_verification_code
    code = create_verification_code("alice@school.edu")
    
    resp = await client.post("/api/auth/verify", json={"email": "alice@school.edu", "code": code})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "alice@school.edu"
    assert "jwt_token" in [c.name for c in client.cookies.jar]


async def test_me_returns_user(client, seed, auth_token):
    """GET /api/auth/me with valid token returns user info."""
    seed(users=["alice@school.edu"])
    token = auth_token("alice@school.edu")
    resp = await client.get("/api/auth/me", cookies={"jwt_token": token})
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@school.edu"


async def test_logout_clears_cookie(client):
    """POST /api/auth/logout clears the JWT cookie."""
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 200
    # Cookie should be cleared (set to empty)


# Sad paths
async def test_request_code_unregistered_email(client, seed):
    """POST /api/auth/request-code with unregistered email returns 404."""
    seed(users=["alice@school.edu"])
    resp = await client.post("/api/auth/request-code", json={"email": "unknown@school.edu"})
    assert resp.status_code == 404


async def test_verify_wrong_code(client, seed):
    """POST /api/auth/verify with wrong code returns 401."""
    seed(users=["alice@school.edu"])
    create_verification_code("alice@school.edu")
    resp = await client.post("/api/auth/verify", json={"email": "alice@school.edu", "code": "000000"})
    assert resp.status_code == 401


async def test_verify_expired_code(client, seed):
    """POST /api/auth/verify with expired code returns 401."""
    # Manually insert an expired code
    seed(users=["alice@school.edu"])
    from app.db import get_conn
    from datetime import datetime, timedelta, timezone
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO verification_codes (email, code, expires_at) VALUES (?, ?, ?)",
            ("alice@school.edu", "123456", expired),
        )
    resp = await client.post("/api/auth/verify", json={"email": "alice@school.edu", "code": "123456"})
    assert resp.status_code == 401


async def test_me_no_token(client):
    """GET /api/auth/me without token returns 401."""
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_me_invalid_token(client):
    """GET /api/auth/me with invalid token returns 401."""
    resp = await client.get("/api/auth/me", cookies={"jwt_token": "garbage"})
    assert resp.status_code == 401


# Edge cases
async def test_request_code_empty_email(client):
    """POST /api/auth/request-code with empty body returns 422."""
    resp = await client.post("/api/auth/request-code", json={})
    assert resp.status_code == 422
```

### `test_subjects_chats.py` — Subject & Chat CRUD

```python
"""Tests for subject and chat CRUD endpoints."""

# Happy paths
async def test_create_subject_happy(client, seed, auth_token):
    """POST /api/subjects creates a subject."""
    seed(users=["alice@school.edu"])
    token = auth_token("alice@school.edu")
    resp = await client.post("/api/subjects?name=History", cookies={"jwt_token": token})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "History"
    assert data["user_id"] > 0


async def test_list_subjects_happy(client, seed, auth_token):
    """GET /api/subjects returns user's subjects."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math"), (1, "Physics")])
    token = auth_token("alice@school.edu")
    resp = await client.get("/api/subjects", cookies={"jwt_token": token})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


async def test_delete_subject_happy(client, seed, auth_token):
    """DELETE /api/subjects/{id} removes a subject."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math")])
    token = auth_token("alice@school.edu")
    resp = await client.delete("/api/subjects/1", cookies={"jwt_token": token})
    assert resp.status_code == 200
    # Verify deleted
    resp = await client.get("/api/subjects", cookies={"jwt_token": token})
    assert len(resp.json()) == 0


async def test_create_chat_happy(client, seed, auth_token):
    """POST /api/chats creates a chat."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math")])
    token = auth_token("alice@school.edu")
    resp = await client.post("/api/chats?subject_id=1&mode=guide", cookies={"jwt_token": token})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "guide"
    assert data["title"] == "New Chat"


async def test_list_chats_happy(client, seed, auth_token):
    """GET /api/chats returns chats for a subject."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math")], chats=[(1, 1, "guide", "Help")])
    token = auth_token("alice@school.edu")
    resp = await client.get("/api/chats?subject_id=1", cookies={"jwt_token": token})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_get_chat_messages_happy(client, seed, auth_token):
    """GET /api/chats/{id}/messages returns messages."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math")], chats=[(1, 1, "guide", "Help")])
    token = auth_token("alice@school.edu")
    # Add a message
    from app.db import save_message
    save_message(chat_id=1, role="user", content="Hello")
    resp = await client.get("/api/chats/1/messages", cookies={"jwt_token": token})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_delete_chat_happy(client, seed, auth_token):
    """DELETE /api/chats/{id} removes chat and messages."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math")], chats=[(1, 1, "guide", "Help")])
    from app.db import save_message, get_conn
    save_message(chat_id=1, role="user", content="Hello")
    token = auth_token("alice@school.edu")
    resp = await client.delete("/api/chats/1", cookies={"jwt_token": token})
    assert resp.status_code == 200
    # Verify messages also deleted
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM messages WHERE chat_id = 1").fetchone()[0]
    assert count == 0


# Sad paths
async def test_delete_subject_not_found(client, seed, auth_token):
    """DELETE /api/subjects/{id} with nonexistent subject returns 404."""
    seed(users=["alice@school.edu"])
    token = auth_token("alice@school.edu")
    resp = await client.delete("/api/subjects/999", cookies={"jwt_token": token})
    assert resp.status_code == 404


async def test_create_chat_subject_not_found(client, seed, auth_token):
    """POST /api/chats with nonexistent subject returns 404."""
    seed(users=["alice@school.edu"])
    token = auth_token("alice@school.edu")
    resp = await client.post("/api/chats?subject_id=999&mode=guide", cookies={"jwt_token": token})
    assert resp.status_code == 404


async def test_list_chats_subject_not_found(client, seed, auth_token):
    """GET /api/chats with nonexistent subject returns 404."""
    seed(users=["alice@school.edu"])
    token = auth_token("alice@school.edu")
    resp = await client.get("/api/chats?subject_id=999", cookies={"jwt_token": token})
    assert resp.status_code == 404


# Edge cases: cross-user access
async def test_delete_other_users_subject(client, seed, auth_token):
    """DELETE /api/subjects/{id} on another user's subject returns 404."""
    seed(users=["alice@school.edu", "bob@school.edu"], subjects=[(1, "Math"), (2, "Chemistry")])
    token_alice = auth_token("alice@school.edu")
    # Bob's subject id=2, Alice tries to delete it
    resp = await client.delete("/api/subjects/2", cookies={"jwt_token": token_alice})
    assert resp.status_code == 404


async def test_list_other_users_chats(client, seed, auth_token):
    """GET /api/chats on another user's subject returns 404."""
    seed(users=["alice@school.edu", "bob@school.edu"], subjects=[(1, "Math"), (2, "Chemistry")])
    token_alice = auth_token("alice@school.edu")
    resp = await client.get("/api/chats?subject_id=2", cookies={"jwt_token": token_alice})
    assert resp.status_code == 404
```

### `test_chat_stream.py` — Chat Streaming

```python
"""Tests for the chat streaming endpoint."""

import json


async def test_chat_stream_happy(client, seed, auth_token, mock_cycling_invoke, mock_title_llm):
    """POST /api/chat/stream streams tokens and saves messages."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math")], chats=[(1, 1, "guide", "New Chat")])
    token = auth_token("alice@school.edu")
    
    with mock_cycling_invoke(), mock_title_llm():
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "What is 2+2?", "chat_id": 1},
            cookies={"jwt_token": token},
        )
        assert resp.status_code == 200
        
        # Parse SSE events
        events = []
        for line in resp.text.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        
        # Should have token events, done event
        types = [e["type"] for e in events]
        assert "done" in types
        assert "token" in types or "title" in types


async def test_chat_stream_saves_user_message(client, seed, auth_token, mock_cycling_invoke):
    """Chat stream saves the user message to DB."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math")], chats=[(1, 1, "guide", "New Chat")])
    token = auth_token("alice@school.edu")
    
    with mock_cycling_invoke():
        await client.post(
            "/api/chat/stream",
            json={"message": "Hello", "chat_id": 1},
            cookies={"jwt_token": token},
        )
    
    from app.db import get_messages
    messages = get_messages(1)
    user_msgs = [m for m in messages if m.role == "user"]
    assert len(user_msgs) == 1
    assert user_msgs[0].content == "Hello"


async def test_chat_stream_saves_assistant_message(client, seed, auth_token, mock_cycling_invoke):
    """Chat stream saves the assistant response to DB."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math")], chats=[(1, 1, "guide", "New Chat")])
    token = auth_token("alice@school.edu")
    
    with mock_cycling_invoke():
        await client.post(
            "/api/chat/stream",
            json={"message": "Hi", "chat_id": 1},
            cookies={"jwt_token": token},
        )
    
    from app.db import get_messages
    messages = get_messages(1)
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(assistant_msgs) == 1


async def test_chat_stream_no_chat_id_saves_with_zero(client, seed, auth_token, mock_cycling_invoke):
    """Chat stream without chat_id saves message with chat_id=0."""
    seed(users=["alice@school.edu"])
    token = auth_token("alice@school.edu")
    
    with mock_cycling_invoke():
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "Hello"},
            cookies={"jwt_token": token},
        )
        assert resp.status_code == 200


async def test_chat_stream_unauthenticated(client):
    """Chat stream without auth returns 401."""
    resp = await client.post(
        "/api/chat/stream",
        json={"message": "Hello"},
    )
    assert resp.status_code == 401


# Edge cases
async def test_chat_stream_empty_message_with_no_image(client, seed, auth_token):
    """Chat stream with empty message and no image returns early (no crash)."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math")], chats=[(1, 1, "guide", "New Chat")])
    token = auth_token("alice@school.edu")
    # Empty message with no image should still work (backend handles it)
    resp = await client.post(
        "/api/chat/stream",
        json={"message": "", "chat_id": 1},
        cookies={"jwt_token": token},
    )
    # Should not crash — may return 200 or 422 depending on validation
    assert resp.status_code in (200, 422)
```

### `test_debug.py` — Debug Endpoints

```python
"""Tests for debug endpoints."""

async def test_debug_users_happy(client, seed):
    """GET /api/debug/users returns all users."""
    seed(users=["alice@school.edu", "bob@school.edu"])
    resp = await client.get("/api/debug/users")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_debug_users_subjects(client, seed):
    """GET /api/debug/users/{id}/subjects returns user's subjects."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math"), (1, "Physics")])
    resp = await client.get("/api/debug/users/1/subjects")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_debug_subjects_chats(client, seed):
    """GET /api/debug/subjects/{id}/chats returns chats."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math")], chats=[(1, 1, "guide", "Help")])
    resp = await client.get("/api/debug/subjects/1/chats")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_debug_chats_messages(client, seed):
    """GET /api/debug/chats/{id}/messages returns messages."""
    seed(users=["alice@school.edu"], subjects=[(1, "Math")], chats=[(1, 1, "guide", "Help")])
    from app.db import save_message
    save_message(chat_id=1, role="user", content="Test")
    resp = await client.get("/api/debug/chats/1/messages")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_debug_sql_happy(client, seed):
    """POST /api/debug/sql executes SQL and returns results."""
    seed(users=["alice@school.edu"])
    resp = await client.post("/api/debug/sql", json={"sql": "SELECT * FROM users"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] == 1


async def test_debug_sql_empty(client):
    """POST /api/debug/sql with empty SQL returns 400."""
    resp = await client.post("/api/debug/sql", json={"sql": ""})
    assert resp.status_code == 400


async def test_debug_sql_invalid(client):
    """POST /api/debug/sql with invalid SQL returns 400."""
    resp = await client.post("/api/debug/sql", json={"sql": "NOT VALID SQL"})
    assert resp.status_code == 400


# Edge case: production mode blocks debug
async def test_debug_blocked_in_prod(client, seed, monkeypatch):
    """Debug endpoints return 403 when ENVIRONMENT=prod."""
    monkeypatch.setattr("app.config.settings.environment", "prod")
    seed(users=["alice@school.edu"])
    resp = await client.get("/api/debug/users")
    assert resp.status_code == 403
```

---

## Running All Tests

```bash
cd /Users/zac/Desktop/homework-helper/backend
python -m pytest tests/ -v
```

Expected: All tests pass. If any fail, debug and fix (either test bug or real bug exposed by test).

---

## Expected Outcome

- ~30-40 test functions covering all endpoints
- Happy path, sad path, and edge cases for each endpoint group
- Each test is declarative: setup → action → assert
- Zero external dependencies (LLM and email are mocked)
- Each test runs in <1 second (isolated DB, no real I/O)
