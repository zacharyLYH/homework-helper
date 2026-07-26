import pytest
from app.db import get_conn


@pytest.fixture
def auth(client, seed):
    seed(users=["alice@school.edu"])

    from app.db import get_conn as _get_conn

    async def _login():
        await client.post("/api/auth/request-code", json={"email": "alice@school.edu"})
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT code FROM verification_codes WHERE email = ?", ("alice@school.edu",)
            ).fetchone()
            code = row["code"]
        await client.post("/api/auth/verify", json={"email": "alice@school.edu", "code": code})
    return _login


async def _login_as(client, email: str):
    await client.post("/api/auth/request-code", json={"email": email})
    with get_conn() as conn:
        code = conn.execute(
            "SELECT code FROM verification_codes WHERE email = ?", (email,)
        ).fetchone()["code"]
    await client.post("/api/auth/verify", json={"email": email, "code": code})


async def test_list_subjects_empty(client, auth):
    await auth()
    resp = await client.get("/api/subjects")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_subject(client, auth):
    await auth()
    resp = await client.post("/api/subjects", params={"name": "Math"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Math"
    assert data["id"] > 0

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subjects WHERE id = ?", (data["id"],)).fetchone()
        assert row is not None
        assert row["name"] == "Math"


async def test_create_and_list_subjects(client, auth):
    await auth()
    await client.post("/api/subjects", params={"name": "Math"})
    await client.post("/api/subjects", params={"name": "Physics"})

    resp = await client.get("/api/subjects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = [s["name"] for s in data]
    assert "Math" in names
    assert "Physics" in names

    with get_conn() as conn:
        rows = conn.execute("SELECT name FROM subjects ORDER BY name").fetchall()
        assert [r["name"] for r in rows] == ["Math", "Physics"]


async def test_create_and_delete_subject(client, auth):
    await auth()
    create_resp = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/subjects/{subject_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["message"] == "Deleted"

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
        assert row is None


async def test_create_chat(client, auth):
    await auth()
    subject_resp = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = subject_resp.json()["id"]

    resp = await client.post("/api/chats", params={"subject_id": subject_id, "mode": "guide", "title": "Algebra"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["subject_id"] == subject_id
    assert data["mode"] == "guide"
    assert data["title"] == "Algebra"

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM chats WHERE id = ?", (data["id"],)).fetchone()
        assert row is not None
        assert row["subject_id"] == subject_id
        assert row["mode"] == "guide"
        assert row["title"] == "Algebra"


async def test_list_chats(client, auth):
    await auth()
    subject_resp = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = subject_resp.json()["id"]
    await client.post("/api/chats", params={"subject_id": subject_id, "mode": "guide", "title": "Algebra"})
    await client.post("/api/chats", params={"subject_id": subject_id, "mode": "just-solve", "title": "Calculus"})

    resp = await client.get("/api/chats", params={"subject_id": subject_id})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    with get_conn() as conn:
        rows = conn.execute("SELECT title FROM chats WHERE subject_id = ? ORDER BY title", (subject_id,)).fetchall()
        assert [r["title"] for r in rows] == ["Algebra", "Calculus"]


async def test_get_chat(client, auth):
    await auth()
    subject_resp = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = subject_resp.json()["id"]
    chat_resp = await client.post("/api/chats", params={"subject_id": subject_id, "mode": "guide"})
    chat_id = chat_resp.json()["id"]

    resp = await client.get(f"/api/chats/{chat_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == chat_id

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        assert row is not None
        assert row["id"] == chat_id


async def test_get_chat_messages(client, auth):
    await auth()
    subject_resp = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = subject_resp.json()["id"]
    chat_resp = await client.post("/api/chats", params={"subject_id": subject_id, "mode": "guide"})
    chat_id = chat_resp.json()["id"]

    resp = await client.get(f"/api/chats/{chat_id}/messages")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_delete_chat(client, auth):
    await auth()
    subject_resp = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = subject_resp.json()["id"]
    chat_resp = await client.post("/api/chats", params={"subject_id": subject_id, "mode": "guide"})
    chat_id = chat_resp.json()["id"]

    del_resp = await client.delete(f"/api/chats/{chat_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["message"] == "Deleted"

    with get_conn() as conn:
        chat_row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        assert chat_row is None
        msg_rows = conn.execute("SELECT * FROM messages WHERE chat_id = ?", (chat_id,)).fetchall()
        assert len(msg_rows) == 0


# ── sad / edge ───────────────────────────────────────────────────────


async def test_subject_no_auth(client, seed):
    seed(users=["alice@school.edu"])
    assert (await client.get("/api/subjects")).status_code == 401
    assert (await client.post("/api/subjects", params={"name": "Math"})).status_code == 401


async def test_subject_not_found(client, seed):
    seed(users=["alice@school.edu"])
    await _login_as(client, "alice@school.edu")
    assert (await client.delete("/api/subjects/9999")).status_code == 404


async def test_subject_owned_by_other_user(client, seed):
    seed(users=["alice@school.edu", "bob@school.edu"])
    await _login_as(client, "alice@school.edu")
    create = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = create.json()["id"]

    client.cookies.clear()
    await _login_as(client, "bob@school.edu")

    assert (await client.get(f"/api/subjects")).json() == []
    assert (await client.post("/api/chats", params={"subject_id": subject_id})).status_code == 404
    assert (await client.get("/api/chats", params={"subject_id": subject_id})).status_code == 404
    assert (await client.get(f"/api/chats/{9999}")).status_code == 404


async def test_chat_no_auth(client, seed):
    seed(users=["alice@school.edu"])
    await _login_as(client, "alice@school.edu")
    create = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = create.json()["id"]
    chat = await client.post("/api/chats", params={"subject_id": subject_id})
    chat_id = chat.json()["id"]

    client.cookies.clear()
    assert (await client.post("/api/chats", params={"subject_id": subject_id})).status_code == 401
    assert (await client.get(f"/api/chats/{chat_id}")).status_code == 401
    assert (await client.get(f"/api/chats/{chat_id}/messages")).status_code == 401
    assert (await client.delete(f"/api/chats/{chat_id}")).status_code == 401


async def test_chat_not_found(client, seed):
    seed(users=["alice@school.edu"])
    await _login_as(client, "alice@school.edu")
    assert (await client.get("/api/chats/9999")).status_code == 404
    assert (await client.get("/api/chats/9999/messages")).status_code == 404
    assert (await client.delete("/api/chats/9999")).status_code == 404


async def test_chat_nonexistent_subject(client, seed):
    seed(users=["alice@school.edu"])
    await _login_as(client, "alice@school.edu")
    assert (await client.post("/api/chats", params={"subject_id": 9999})).status_code == 404


async def test_chat_owned_by_other_user(client, seed):
    seed(users=["alice@school.edu", "bob@school.edu"])
    await _login_as(client, "alice@school.edu")
    create = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = create.json()["id"]
    chat = await client.post("/api/chats", params={"subject_id": subject_id})
    chat_id = chat.json()["id"]

    client.cookies.clear()
    await _login_as(client, "bob@school.edu")

    assert (await client.get(f"/api/chats/{chat_id}")).status_code == 404
    assert (await client.get(f"/api/chats/{chat_id}/messages")).status_code == 404
    assert (await client.delete(f"/api/chats/{chat_id}")).status_code == 404
