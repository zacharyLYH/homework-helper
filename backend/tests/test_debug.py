from app.db import get_conn
from tests.seed import INITIAL_SEED


async def test_debug_users_empty(client):
    resp = await client.get("/api/debug/users")
    assert resp.status_code == 200
    assert resp.json() == []

    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        assert count == 0


async def test_debug_users(client, seed):
    seed(sql=INITIAL_SEED)
    resp = await client.get("/api/debug/users")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    emails = [u["email"] for u in data]
    assert "alice@school.edu" in emails

    with get_conn() as conn:
        rows = conn.execute("SELECT email FROM users ORDER BY email").fetchall()
        assert [r["email"] for r in rows] == ["alice@school.edu", "bob@school.edu"]


async def test_debug_subjects(client, seed):
    seed(sql=INITIAL_SEED)
    resp = await client.get("/api/debug/users/1/subjects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = [s["name"] for s in data]
    assert "Math" in names

    with get_conn() as conn:
        rows = conn.execute("SELECT name FROM subjects WHERE user_id = 1 ORDER BY name").fetchall()
        assert [r["name"] for r in rows] == ["Math", "Physics"]


async def test_debug_chats(client, seed):
    seed(sql=INITIAL_SEED)
    resp = await client.get("/api/debug/subjects/1/chats")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM chats WHERE subject_id = 1").fetchone()["c"]
        assert count == 2


async def test_debug_messages(client, seed):
    seed(sql=INITIAL_SEED)
    resp = await client.get("/api/debug/chats/1/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    with get_conn() as conn:
        rows = conn.execute("SELECT role, content FROM messages WHERE chat_id = 1 ORDER BY created_at").fetchall()
        assert len(rows) == 2
        assert rows[0]["role"] == "user"
        assert rows[0]["content"] == "What is 2+2?"


async def test_debug_sql_select(client, seed):
    seed(sql=INITIAL_SEED)
    resp = await client.post("/api/debug/sql", json={"sql": "SELECT email FROM users ORDER BY email"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] == 2
    assert data["rows"][0]["email"] == "alice@school.edu"


async def test_debug_sql_insert(client):
    resp = await client.post("/api/debug/sql", json={"sql": "INSERT INTO users (email) VALUES ('test@test.com')"})
    assert resp.status_code == 200
    assert resp.json()["row_count"] == 0

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = 'test@test.com'").fetchone()
        assert row is not None
        assert row["email"] == "test@test.com"
