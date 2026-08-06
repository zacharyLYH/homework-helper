from app.db import get_conn
from app.main import app as fastapi_app
from memory import db as memory_db


async def _login_as(client, email: str) -> None:
    await client.post("/api/auth/request-code", json={"email": email})
    with get_conn() as conn:
        row = conn.execute(
            "SELECT code FROM verification_codes WHERE email = ?",
            (email,),
        ).fetchone()
        assert row is not None
        code = row["code"]
    await client.post("/api/auth/verify", json={"email": email, "code": code})


async def test_memory_routes_disabled_return_503_contract(client, seed):
    seed(users=["alice@school.edu"])
    await _login_as(client, "alice@school.edu")
    subject_resp = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = subject_resp.json()["id"]

    resp = await client.get(f"/api/memory/subjects/{subject_id}/context")

    assert resp.status_code == 503
    data = resp.json()
    assert "detail" in data
    assert data["detail"]["error"] == "memory_disabled"
    assert "reason" in data["detail"]
    assert data["detail"]["message"] == "Memory subsystem is disabled"


async def test_memory_routes_enabled_return_data(client, seed, tmp_path, monkeypatch):
    seed(users=["alice@school.edu"])
    await _login_as(client, "alice@school.edu")

    subject_resp = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = subject_resp.json()["id"]

    with get_conn() as conn:
        user_row = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            ("alice@school.edu",),
        ).fetchone()
        assert user_row is not None
        user_id = int(user_row["id"])

    memory_db_path = tmp_path / "memory.db"
    memory_db.init_db(memory_db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", memory_db_path)
    prev_enabled = getattr(fastapi_app.state, "memory_enabled", False)
    prev_reason = getattr(fastapi_app.state, "memory_status_reason", "unknown")
    fastapi_app.state.memory_enabled = True
    fastapi_app.state.memory_status_reason = "memory_enabled"

    try:
        with memory_db.get_conn(memory_db_path) as conn:
            conn.execute(
                """
                INSERT INTO learner_observations (user_id, subject_id, observation, source)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, subject_id, "Confuses distributive sign", "chat"),
            )
            conn.execute(
                """
                INSERT INTO memory_update_jobs (user_id, subject_id, chat_id, status, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, subject_id, None, "pending", '{"trigger":"chat_turn"}'),
            )

        context_resp = await client.get(f"/api/memory/subjects/{subject_id}/context")
        jobs_resp = await client.get(f"/api/memory/subjects/{subject_id}/jobs")

        assert context_resp.status_code == 200
        context_data = context_resp.json()
        assert context_data["memory_loaded"] is True
        assert "Recent learner observations" in context_data["memory_context"]

        assert jobs_resp.status_code == 200
        jobs_data = jobs_resp.json()
        assert len(jobs_data["jobs"]) == 1
        assert jobs_data["jobs"][0]["status"] == "pending"
    finally:
        fastapi_app.state.memory_enabled = prev_enabled
        fastapi_app.state.memory_status_reason = prev_reason


async def test_memory_routes_authz_subject_scoped(client, seed, tmp_path, monkeypatch):
    seed(users=["alice@school.edu", "bob@school.edu"])
    await _login_as(client, "alice@school.edu")

    subject_resp = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = subject_resp.json()["id"]

    memory_db_path = tmp_path / "memory.db"
    memory_db.init_db(memory_db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", memory_db_path)
    prev_enabled = getattr(fastapi_app.state, "memory_enabled", False)
    prev_reason = getattr(fastapi_app.state, "memory_status_reason", "unknown")
    fastapi_app.state.memory_enabled = True
    fastapi_app.state.memory_status_reason = "memory_enabled"

    try:
        client.cookies.clear()
        await _login_as(client, "bob@school.edu")

        resp = await client.get(f"/api/memory/subjects/{subject_id}/context")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Subject not found"
    finally:
        fastapi_app.state.memory_enabled = prev_enabled
        fastapi_app.state.memory_status_reason = prev_reason
