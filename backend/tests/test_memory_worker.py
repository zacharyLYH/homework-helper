import json
from unittest.mock import patch

import httpx

from memory import db as memory_db
from memory.jobs import process_pending_jobs
from memory.service import enqueue_memory_update, load_memory_context


def test_memory_worker_processes_pending_jobs(tmp_path, monkeypatch) -> None:
    memory_db_path = tmp_path / "memory.db"
    memory_db.init_db(memory_db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", memory_db_path)

    job_id = enqueue_memory_update(
        user_id=11,
        subject_id=7,
        chat_id=99,
        payload={
            "trigger": "chat_turn",
            "messages": [
                {"role": "user", "content": "I keep flipping signs in quadratic formula"},
                {"role": "assistant", "content": "Track b^2 - 4ac carefully"},
            ],
        },
    )

    result = process_pending_jobs(batch_size=5)

    assert result.claimed == 1
    assert result.done == 1
    assert result.failed == 0

    with memory_db.get_conn(memory_db_path) as conn:
        job = conn.execute(
            "SELECT status FROM memory_update_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        assert job is not None
        assert job["status"] == "done"

        obs = conn.execute(
            """
            SELECT observation, source
            FROM learner_observations
            WHERE user_id = ? AND subject_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (11, 7),
        ).fetchone()
        assert obs is not None
        assert obs["source"] == "memory_worker"
        assert "Learner said" in obs["observation"]

        version = conn.execute(
            """
            SELECT mv.version, mv.summary
            FROM memory_current mc
            JOIN memory_versions mv ON mv.id = mc.version_id
            WHERE mc.user_id = ? AND mc.subject_id = ?
            """,
            (11, 7),
        ).fetchone()
        assert version is not None
        assert version["version"] == 1
        assert "Recent learner observations" in version["summary"]

    context = load_memory_context(user_id=11, subject_id=7)
    assert "Recent learner observations" in context


def test_memory_worker_failure_is_isolated_from_next_jobs(tmp_path, monkeypatch) -> None:
    memory_db_path = tmp_path / "memory.db"
    memory_db.init_db(memory_db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", memory_db_path)

    with memory_db.get_conn(memory_db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_update_jobs (user_id, subject_id, chat_id, status, payload_json)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (1, 1, None, "{not-valid-json"),
        )

    good_job_id = enqueue_memory_update(
        user_id=1,
        subject_id=1,
        chat_id=None,
        payload={
            "trigger": "chat_turn",
            "messages": [{"role": "user", "content": "I understand factoring now"}],
        },
    )

    result = process_pending_jobs(batch_size=10)

    assert result.claimed == 2
    assert result.done == 1
    assert result.failed == 1

    with memory_db.get_conn(memory_db_path) as conn:
        rows = conn.execute(
            "SELECT id, status, payload_json FROM memory_update_jobs ORDER BY id ASC"
        ).fetchall()

    assert len(rows) == 2
    assert rows[0]["status"] == "failed"
    failed_payload = json.loads(rows[0]["payload_json"])
    assert "worker_error" in failed_payload

    assert rows[1]["id"] == good_job_id
    assert rows[1]["status"] == "done"


def test_memory_worker_uses_llm_observation_when_config_exists(tmp_path, monkeypatch, setup_test_db):
    """With a user LLM config present, the worker stores the model's observation."""
    from app.db import get_conn as app_get_conn
    from tests.mockers import seed_llm_config

    with app_get_conn() as conn:
        conn.execute("INSERT INTO users (email) VALUES ('llm@school.edu')")
        row = conn.execute("SELECT id FROM users WHERE email = 'llm@school.edu'").fetchone()
        user_id = row["id"]
    seed_llm_config(user_id)

    memory_db_path = tmp_path / "memory.db"
    memory_db.init_db(memory_db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", memory_db_path)

    job_id = enqueue_memory_update(
        user_id=user_id,
        subject_id=3,
        chat_id=None,
        payload={
            "trigger": "chat_turn",
            "messages": [
                {"role": "user", "content": "I keep confusing coefficients in factoring"},
                {"role": "assistant", "content": "Rewrite ax^2 + bx + c and check signs"},
            ],
        },
    )

    async def _handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        req = json.loads(body) if body else {}
        prompt = "".join(m["content"] for m in req.get("messages", []))
        assert "factoring" in prompt, "memory LLM prompt should include the learner messages"
        resp = {
            "id": "cmpl",
            "object": "chat.completion",
            "model": "gpt-4",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Struggles with sign errors when factoring quadratics."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
        }
        return httpx.Response(200, json=resp)

    transport = httpx.MockTransport(_handler)
    mock_client = httpx.AsyncClient(transport=transport)
    with patch(
        "langchain_openai.chat_models.base._get_default_async_httpx_client",
        return_value=mock_client,
    ):
        result = process_pending_jobs(batch_size=5)

    assert result.claimed == 1
    assert result.done == 1

    with memory_db.get_conn(memory_db_path) as conn:
        obs = conn.execute(
            "SELECT observation, source FROM learner_observations WHERE user_id = ? AND subject_id = ?",
            (user_id, 3),
        ).fetchone()
    assert obs["source"] == "memory_worker"
    assert obs["observation"] == "Struggles with sign errors when factoring quadratics."
