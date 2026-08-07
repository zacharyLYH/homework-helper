import os

from app.db import get_conn, get_debug_conn
from tests.seed import INITIAL_SEED

DEBUG_EMAIL = "leeyihong03@gmail.com"


def _auth_headers(auth_token) -> dict:
    return {"Authorization": f"Bearer {auth_token(DEBUG_EMAIL)}"}


def _seed_main(sql: str) -> None:
    with get_conn() as conn:
        conn.executescript(sql)


def _seed_debug(sql: str) -> None:
    with get_debug_conn() as conn:
        conn.executescript(sql)


async def test_debug_users_only_debug_user(client, auth_token):
    """Debug DB holds structured_logs only; main DB holds app users."""
    headers = _auth_headers(auth_token)
    resp = await client.get("/api/debug/users", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1  # the debug user created by auth_token lives in main DB
    assert data[0]["email"] == DEBUG_EMAIL

    with get_debug_conn() as conn:
        tables = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert tables == {"structured_logs"}

    with get_conn() as conn:
        tables = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "structured_logs" not in tables


async def test_debug_users(client, seed, auth_token):
    _seed_main(INITIAL_SEED)
    headers = _auth_headers(auth_token)
    resp = await client.get("/api/debug/users", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    emails = [u["email"] for u in data]
    assert "alice@school.edu" in emails

    with get_conn() as conn:
        rows = conn.execute("SELECT email FROM users ORDER BY email").fetchall()
        assert [r["email"] for r in rows] == ["alice@school.edu", "bob@school.edu", "leeshihau@gmail.com", "leeyihong03@gmail.com"]


async def test_debug_subjects(client, seed, auth_token):
    _seed_main(INITIAL_SEED)
    headers = _auth_headers(auth_token)
    resp = await client.get("/api/debug/users/1/subjects", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = [s["name"] for s in data]
    assert "Math" in names

    with get_conn() as conn:
        rows = conn.execute("SELECT name FROM subjects WHERE user_id = 1 ORDER BY name").fetchall()
        assert [r["name"] for r in rows] == ["Math", "Physics"]


async def test_debug_chats(client, seed, auth_token):
    _seed_main(INITIAL_SEED)
    headers = _auth_headers(auth_token)
    resp = await client.get("/api/debug/subjects/1/chats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM chats WHERE subject_id = 1").fetchone()["c"]
        assert count == 2


async def test_debug_messages(client, seed, auth_token):
    _seed_main(INITIAL_SEED)
    headers = _auth_headers(auth_token)
    resp = await client.get("/api/debug/chats/1/messages", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    with get_conn() as conn:
        rows = conn.execute("SELECT role, content FROM messages WHERE chat_id = 1 ORDER BY created_at").fetchall()
        assert len(rows) == 2
        assert rows[0]["role"] == "user"
        assert rows[0]["content"] == "What is 2+2?"


async def test_debug_sql_select(client, seed, auth_token):
    _seed_main(INITIAL_SEED)
    headers = _auth_headers(auth_token)
    resp = await client.post("/api/debug/sql", json={"sql": "SELECT email FROM users ORDER BY email"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] == 4
    assert data["rows"][0]["email"] == "alice@school.edu"


async def test_debug_sql_insert(client, auth_token):
    headers = _auth_headers(auth_token)
    resp = await client.post("/api/debug/sql", json={"sql": "INSERT INTO users (email) VALUES ('test@test.com')"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["row_count"] == 0

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = 'test@test.com'").fetchone()
        assert row is not None
        assert row["email"] == "test@test.com"


async def test_debug_access_denied(client, seed, auth_token):
    """Non-debug users should get 403."""
    _seed_main(INITIAL_SEED)
    token = auth_token("alice@school.edu")
    resp = await client.get("/api/debug/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


async def test_debug_no_auth(client):
    resp = await client.get("/api/debug/users")
    assert resp.status_code == 401


# ── structured logs / traces ──────────────────────────────────────────


def _seed_one_message_with_log():
    """Helper: seed a user → subject → chat → message (main DB) + structured_log (debug DB)."""
    _seed_main("""
        INSERT INTO users (id, email, created_at) VALUES (10, 'trace@test.com', '2025-01-01T00:00:00');
        INSERT INTO subjects (id, user_id, name, created_at) VALUES (10, 10, 'Test Subject', '2025-01-01T00:00:00');
        INSERT INTO chats (id, subject_id, user_id, title, created_at, updated_at) VALUES
            (10, 10, 10, 'Test Chat', '2025-01-01T00:00:00', '2025-01-01T00:00:00');
        INSERT INTO messages (id, chat_id, role, content, token_count, created_at) VALUES
            (100, 10, 'user', 'hello world', 2, '2025-01-01T00:00:00');
    """)
    _seed_debug("""
        INSERT INTO structured_logs (type, created_at, message_id, log, _req_id) VALUES
            ('chat_request', '2025-01-01T00:00:00', 100, '{"msg":"hello"}', 'req1');
    """)


async def test_traces_happy(client, seed, auth_token):
    _seed_one_message_with_log()
    headers = _auth_headers(auth_token)

    resp = await client.get("/api/debug/traces", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1

    entry = data[0]
    assert entry["id"] == 100
    assert entry["content"] == "hello world"
    assert entry["role"] == "user"
    assert entry["chat_title"] == "Test Chat"
    assert entry["subject_name"] == "Test Subject"
    assert entry["user_email"] == "trace@test.com"


async def test_traces_empty(client, seed, auth_token):
    headers = _auth_headers(auth_token)
    resp = await client.get("/api/debug/traces", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_traces_multiple(client, seed, auth_token):
    _seed_one_message_with_log()
    headers = _auth_headers(auth_token)

    _seed_main("""
        INSERT INTO messages (id, chat_id, role, content, token_count, created_at) VALUES
            (101, 10, 'assistant', 'hi back', 2, '2025-01-01T00:00:01');
    """)
    _seed_debug("""
        INSERT INTO structured_logs (type, created_at, message_id, log, _req_id) VALUES
            ('chat_response', '2025-01-01T00:00:01', 101, '{"msg":"back"}', 'req1');
    """)

    resp = await client.get("/api/debug/traces", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


async def test_traces_sad_no_join_data(client, seed, auth_token):
    """Message with log but no chat/subject/user — nullable fields should be None."""
    headers = _auth_headers(auth_token)
    _seed_main("INSERT INTO messages (id, chat_id, role, content, token_count, created_at) VALUES (200, 0, 'user', 'orphan', 0, '2025-01-01T00:00:00')")
    _seed_debug("INSERT INTO structured_logs (type, created_at, message_id, log, _req_id) VALUES ('test', '2025-01-01T00:00:00', 200, '{}', 'r2')")

    resp = await client.get("/api/debug/traces", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    entry = data[0]
    assert entry["chat_title"] is None
    assert entry["subject_name"] is None
    assert entry["user_email"] is None


async def test_logs_empty(client, seed, auth_token):
    headers = _auth_headers(auth_token)
    resp = await client.get("/api/debug/logs", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_logs_happy(client, seed, auth_token):
    _seed_one_message_with_log()
    headers = _auth_headers(auth_token)

    resp = await client.get("/api/debug/logs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["type"] == "chat_request"
    assert data[0]["message_id"] == 100


async def test_logs_filter_by_message(client, seed, auth_token):
    _seed_one_message_with_log()
    headers = _auth_headers(auth_token)

    resp = await client.get("/api/debug/logs?message_id=100", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["message_id"] == 100

    resp = await client.get("/api/debug/logs?message_id=999", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_logs_sad_no_message_id(client, seed, auth_token):
    """Log with NULL message_id should appear in unfiltered list."""
    headers = _auth_headers(auth_token)
    _seed_debug("INSERT INTO structured_logs (type, created_at, message_id, log, _req_id) VALUES ('orphan', '2025-01-01T00:00:00', NULL, '{}', 'r3')")

    resp = await client.get("/api/debug/logs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["message_id"] is None
