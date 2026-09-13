import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from app.db import get_debug_conn
from app.main import app
from memory import db as memory_db
from memory.jobs.main import process_pending_jobs
from memory.schemas import MemoryEvaluation

from tests.mockers import mock_llm, mock_title_llm, seed_llm_config


@pytest.fixture(autouse=True)
def restore_memory_app_state():
    previous_enabled = getattr(app.state, "memory_enabled", False)
    previous_reason = getattr(app.state, "memory_status_reason", "unknown")
    yield
    app.state.memory_enabled = previous_enabled
    app.state.memory_status_reason = previous_reason


async def _create_chat(client, email: str = "alice@school.edu") -> tuple[int, int, int]:
    with patch("app.routes.auth.send_verification_email", return_value=True):
        await client.post("/api/auth/request-code", json={"email": email})
    from app.db import get_conn

    with get_conn() as conn:
        code = conn.execute(
            "SELECT code FROM verification_codes WHERE email = ?", (email,)
        ).fetchone()["code"]
        user_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()["id"]
    await client.post("/api/auth/verify", json={"email": email, "code": code})
    subject_id = (await client.post("/api/subjects", params={"name": "Math"})).json()[
        "id"
    ]
    chat_id = (
        await client.post("/api/chats", params={"subject_id": subject_id})
    ).json()["id"]
    return int(user_id), int(subject_id), int(chat_id)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token_for(email: str) -> str:
    from app.auth import create_access_token
    from app.db import get_conn
    from app.schemas import User

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return create_access_token(
        User(id=row["id"], email=row["email"], created_at=row["created_at"])
    )


def _evaluation(
    *,
    observation: str = "Learner confuses the signs in the quadratic formula",
    updated_summary: str = "Learner needs practice tracking signs in the quadratic formula.",
) -> MemoryEvaluation:
    from memory.schemas import ConceptStateDelta, ConceptUpsert

    return MemoryEvaluation(
        skip=False,
        observations=[observation],
        concept_upserts=[ConceptUpsert("quadratic_formula", "Quadratic Formula", [])],
        concept_edges=[],
        concept_state_deltas=[ConceptStateDelta("quadratic_formula", 0.3, 0.9)],
        trait_updates={"pace": "careful"},
        updated_summary=updated_summary,
    )


async def test_memory_e2e_chat_worker_and_context_api(
    client, seed, tmp_path, monkeypatch
) -> None:
    seed(users=["alice@school.edu"])
    user_id, subject_id, chat_id = await _create_chat(client)
    token = _token_for("alice@school.edu")
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    app.state.memory_enabled = True
    app.state.memory_status_reason = "memory_enabled"
    seed_llm_config(user_id)

    with mock_llm("The answer is 4."), mock_title_llm("Quadratics"):
        response = await client.post(
            "/api/chat/stream",
            json={
                "message": "For my algebra homework, I keep making sign mistakes in the quadratic formula",
                "chat_id": chat_id,
            },
            headers=_auth_header(token),
        )

    assert response.status_code == 200
    assert '"type": "done"' in response.text
    job = None
    with memory_db.get_conn(db_path) as conn:
        job = conn.execute(
            "SELECT id, status, payload_json FROM memory_update_jobs"
        ).fetchone()
    assert job is not None
    assert job["status"] == "pending"
    payload = json.loads(job["payload_json"])
    assert payload["trigger"] == "chat_turn"
    assert payload["messages"]

    with patch(
        "memory.jobs.main.evaluate_memory",
        new=AsyncMock(return_value=_evaluation()),
    ):
        result = await asyncio.to_thread(process_pending_jobs, batch_size=1)

    assert result.claimed == 1
    assert result.done == 1
    assert result.failed == 0

    context_response = await client.get(
        f"/api/memory/subjects/{subject_id}/context", headers=_auth_header(token)
    )
    assert context_response.status_code == 200
    context = context_response.json()
    assert context["memory_loaded"] is True
    assert "Quadratic Formula" in context["memory_context"]
    assert "Learner confuses" in context["memory_context"]
    assert "pace: careful" in context["memory_context"]

    jobs_response = await client.get(
        f"/api/memory/subjects/{subject_id}/jobs", headers=_auth_header(token)
    )
    assert jobs_response.status_code == 200
    assert jobs_response.json()["jobs"][0]["status"] == "done"


async def test_memory_e2e_subsequent_chat_injects_persisted_context(
    client, seed, tmp_path, monkeypatch
) -> None:
    seed(users=["alice@school.edu"])
    user_id, _, chat_id = await _create_chat(client)
    token = _token_for("alice@school.edu")
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    app.state.memory_enabled = True
    app.state.memory_status_reason = "memory_enabled"
    seed_llm_config(user_id)

    with mock_llm("The answer is 4."), mock_title_llm("First Chat"):
        first_response = await client.post(
            "/api/chat/stream",
            json={
                "message": "For my algebra homework, I keep making sign mistakes in the quadratic formula",
                "chat_id": chat_id,
            },
            headers=_auth_header(token),
        )
    assert first_response.status_code == 200

    with patch(
        "memory.jobs.main.evaluate_memory",
        new=AsyncMock(return_value=_evaluation()),
    ):
        result = await asyncio.to_thread(process_pending_jobs, batch_size=1)
    assert result.done == 1

    captured: dict[str, list] = {}

    async def capture_stream(messages, **_kwargs):
        from langchain_core.messages import AIMessageChunk

        captured["messages"] = messages
        yield AIMessageChunk(content="Keep track of each sign.")

    with (
        patch("app.graph.llm_router.stream", new=capture_stream),
        mock_title_llm("Follow-up"),
    ):
        response = await client.post(
            "/api/chat/stream",
            json={
                "message": "How should I avoid that mistake?",
                "chat_id": chat_id,
            },
            headers=_auth_header(token),
        )

    assert response.status_code == 200
    system_prompt = captured["messages"][0].content
    assert "Learner needs practice tracking signs" in system_prompt
    assert "Learner confuses the signs" in system_prompt
    assert "Learner needs practice tracking signs" not in response.text
    with get_debug_conn() as conn:
        injected = conn.execute(
            "SELECT 1 FROM structured_logs WHERE type = ? LIMIT 1",
            ("memory_context_injected",),
        ).fetchone()
    assert injected is not None


async def test_memory_e2e_jobs_are_not_visible_to_another_user(
    client, seed, tmp_path, monkeypatch
) -> None:
    seed(users=["alice@school.edu", "bob@school.edu"])
    alice_id, subject_id, _chat_id = await _create_chat(client, "alice@school.edu")
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    app.state.memory_enabled = True
    app.state.memory_status_reason = "memory_enabled"
    with memory_db.get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO memory_update_jobs (user_id, subject_id, status) VALUES (?, ?, 'pending')",
            (alice_id, subject_id),
        )

    await _create_chat(client, "bob@school.edu")
    response = await client.get(
        f"/api/memory/subjects/{subject_id}/jobs",
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Subject not found"


async def test_memory_e2e_context_isolated_between_subjects(
    client, seed, tmp_path, monkeypatch
) -> None:
    seed(users=["alice@school.edu"])
    user_id, first_subject_id, _chat_id = await _create_chat(client)
    token = _token_for("alice@school.edu")
    second_subject_id = (
        await client.post("/api/subjects", params={"name": "Physics"})
    ).json()["id"]
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    app.state.memory_enabled = True
    app.state.memory_status_reason = "memory_enabled"
    with memory_db.get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO memory_summary (user_id, subject_id, summary) VALUES (?, ?, ?)",
            (user_id, first_subject_id, "Learner needs sign-tracking practice."),
        )

    response = await client.get(
        f"/api/memory/subjects/{second_subject_id}/context",
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["memory_loaded"] is False
    assert response.json()["memory_context"] == ""


async def test_memory_e2e_disabled_chat_succeeds_without_memory_job(
    client, seed, tmp_path, monkeypatch
) -> None:
    seed(users=["alice@school.edu"])
    user_id, subject_id, chat_id = await _create_chat(client)
    token = _token_for("alice@school.edu")
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    app.state.memory_enabled = False
    app.state.memory_status_reason = "disabled_by_config"
    seed_llm_config(user_id)

    with mock_llm("The answer is 4."), mock_title_llm("No Memory"):
        response = await client.post(
            "/api/chat/stream",
            json={
                "message": "Help me solve this calculus homework problem",
                "chat_id": chat_id,
            },
            headers=_auth_header(token),
        )

    assert response.status_code == 200
    assert '"type": "done"' in response.text
    with memory_db.get_conn(db_path) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM memory_update_jobs").fetchone()[0] == 0
        )
    context_response = await client.get(
        f"/api/memory/subjects/{subject_id}/context", headers=_auth_header(token)
    )
    assert context_response.status_code == 503
    assert context_response.json()["detail"]["error"] == "memory_disabled"


async def test_memory_e2e_invalid_llm_schema_fails_job_without_invalid_rows(
    client, seed, tmp_path, monkeypatch
) -> None:
    seed(users=["alice@school.edu"])
    user_id, _subject_id, chat_id = await _create_chat(client)
    token = _token_for("alice@school.edu")
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    app.state.memory_enabled = True
    app.state.memory_status_reason = "memory_enabled"
    seed_llm_config(user_id)

    with mock_llm("The answer is 4."), mock_title_llm("Invalid Schema"):
        response = await client.post(
            "/api/chat/stream",
            json={
                "message": "Help me with this algebra homework question",
                "chat_id": chat_id,
            },
            headers=_auth_header(token),
        )
    assert response.status_code == 200

    invalid_llm = type(
        "InvalidLLM",
        (),
        {
            "ainvoke": AsyncMock(
                return_value=type(
                    "Response",
                    (),
                    {
                        "content": '{"concept_edges": [{"from_concept_key": "a", "to_concept_key": "b", "relation": "invalid", "weight": 0.5}]}'
                    },
                )()
            )
        },
    )()
    with patch("memory.llm._make_llm", return_value=invalid_llm):
        result = await asyncio.to_thread(process_pending_jobs, batch_size=1)

    assert result.claimed == 1
    assert result.done == 0
    assert result.failed == 1
    with memory_db.get_conn(db_path) as conn:
        job = conn.execute(
            "SELECT status, payload_json FROM memory_update_jobs"
        ).fetchone()
        assert job["status"] == "failed"
        assert "worker_error" in json.loads(job["payload_json"])
        assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 0

