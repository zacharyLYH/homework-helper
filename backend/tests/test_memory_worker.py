import json
from unittest.mock import AsyncMock, patch

from app import structured_log as structured_log_module
from app.db import get_debug_conn
from memory import db as memory_db
from memory.jobs.main import process_pending_jobs
from memory.llm import _resolve_memory_llm
from memory.schemas import MemoryEvaluation, ConceptUpsert, ConceptEdgeUpsert, ConceptStateDelta
from memory.service.main import enqueue_memory_update, load_memory_context
from shared.schemas import MemoryUpdatePayload


def _make_evaluation(**overrides) -> MemoryEvaluation:
    defaults = dict(
        skip=False,
        observations=["Learner struggles with sign flipping in quadratic formula"],
        concept_upserts=[ConceptUpsert(concept_key="quadratic_formula", display_name="Quadratic Formula", aliases=[])],
        concept_edges=[],
        concept_state_deltas=[ConceptStateDelta(concept_key="quadratic_formula", mastery=0.3, confidence=0.8)],
        trait_updates={},
        updated_summary="Learner has difficulty with sign tracking in the quadratic formula.",
    )
    return MemoryEvaluation(**{**defaults, **overrides})


def _make_payload(messages: list[dict[str, str]]) -> MemoryUpdatePayload:
    return {
        "trigger": "chat_turn",
        "memory_loaded": False,
        "memory_context": "",
        "messages": messages,
    }


def test_memory_worker_processes_pending_jobs(tmp_path, monkeypatch) -> None:
    memory_db_path = tmp_path / "memory.db"
    memory_db.init_db(memory_db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", memory_db_path)

    decision = enqueue_memory_update(
        user_id=11,
        subject_id=7,
        chat_id=99,
        payload=_make_payload(
            [
                {"role": "user", "content": "I keep flipping signs in quadratic formula"},
                {"role": "assistant", "content": "Track b^2 - 4ac carefully"},
            ]
        ),
    )
    job_id = decision.job_id
    assert decision.enqueued

    mock_eval = _make_evaluation()

    with patch("memory.jobs.main.evaluate_memory", new=AsyncMock(return_value=mock_eval)):
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
        assert obs["observation"] == "Learner struggles with sign flipping in quadratic formula"

        version = conn.execute(
            """
            SELECT summary
            FROM memory_summary
            WHERE user_id = ? AND subject_id = ?
            """,
            (11, 7),
        ).fetchone()
        assert version is not None
        assert version["summary"] == "Learner has difficulty with sign tracking in the quadratic formula."

        concept = conn.execute(
            "SELECT id FROM concepts WHERE subject_id = ? AND concept_key = ?",
            (7, "quadratic_formula"),
        ).fetchone()
        assert concept is not None

        state = conn.execute(
            "SELECT mastery, confidence FROM learner_concept_state WHERE user_id = ? AND concept_id = ?",
            (11, concept["id"]),
        ).fetchone()
        assert state is not None
        assert abs(state["mastery"] - 0.3) < 0.001

    context = load_memory_context(user_id=11, subject_id=7)
    assert "quadratic" in context.rendered.lower()


def test_memory_worker_skip_does_not_write(tmp_path, monkeypatch) -> None:
    memory_db_path = tmp_path / "memory.db"
    memory_db.init_db(memory_db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", memory_db_path)

    decision = enqueue_memory_update(
        user_id=5,
        subject_id=3,
        chat_id=None,
        payload=_make_payload(
            [{"role": "user", "content": "ok thanks, I think I understand the concept now"}]
        ),
    )
    assert decision.enqueued

    mock_eval = _make_evaluation(
        skip=True,
        observations=[],
        concept_upserts=[],
        concept_edges=[],
        concept_state_deltas=[],
        trait_updates={},
        updated_summary="",
    )

    with patch("memory.jobs.main.evaluate_memory", new=AsyncMock(return_value=mock_eval)):
        result = process_pending_jobs(batch_size=5)

    assert result.claimed == 1
    assert result.done == 1
    assert result.failed == 0

    with memory_db.get_conn(memory_db_path) as conn:
        obs_count = conn.execute(
            "SELECT COUNT(*) as n FROM learner_observations WHERE user_id = ? AND subject_id = ?",
            (5, 3),
        ).fetchone()["n"]
        assert obs_count == 0


def test_memory_worker_preserves_enqueue_trace_id(tmp_path, monkeypatch) -> None:
    memory_db_path = tmp_path / "memory.db"
    memory_db.init_db(memory_db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", memory_db_path)

    request_logger = structured_log_module.StructuredLogger(should_commit=True)
    request_logger._req_id = "chat-request-trace"
    logger_token = structured_log_module._logger_var.set(request_logger)
    try:
        decision = enqueue_memory_update(
            user_id=9,
            subject_id=8,
            chat_id=None,
            payload=_make_payload(
                [{"role": "user", "content": "I need help understanding the chain rule today"}]
            ),
        )
    finally:
        structured_log_module._logger_var.reset(logger_token)
    assert decision.enqueued

    with memory_db.get_conn(memory_db_path) as conn:
        job = conn.execute(
            "SELECT trace_id FROM memory_update_jobs WHERE id = ?", (decision.job_id,)
        ).fetchone()
        assert job is not None
        assert job["trace_id"] == "chat-request-trace"

    with patch("memory.jobs.main.evaluate_memory", new=AsyncMock(return_value=_make_evaluation(skip=True))):
        result = process_pending_jobs(batch_size=1)
    assert result.done == 1

    with get_debug_conn() as conn:
        rows = conn.execute(
            "SELECT type, _req_id FROM structured_logs WHERE type LIKE 'memory_worker_%'"
        ).fetchall()
    assert rows
    assert {row["_req_id"] for row in rows} == {"chat-request-trace"}


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

    decision = enqueue_memory_update(
        user_id=1,
        subject_id=2,
        chat_id=None,
        payload=_make_payload(
            [{"role": "user", "content": "I understand factoring now"}]
        ),
    )
    good_job_id = decision.job_id
    assert decision.enqueued

    mock_eval = _make_evaluation(
        observations=["Learner understands factoring"],
        concept_upserts=[],
        concept_state_deltas=[],
        updated_summary="Learner understands factoring.",
    )

    with patch("memory.jobs.main.evaluate_memory", new=AsyncMock(return_value=mock_eval)):
        result = process_pending_jobs(batch_size=10)

    assert result.claimed == 2
    assert result.done == 1
    assert result.failed == 1

    rows = []
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


def test_memory_worker_llm_error_marks_job_failed(tmp_path, monkeypatch) -> None:
    memory_db_path = tmp_path / "memory.db"
    memory_db.init_db(memory_db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", memory_db_path)

    decision = enqueue_memory_update(
        user_id=2,
        subject_id=4,
        chat_id=None,
        payload=_make_payload(
            [{"role": "user", "content": "can you help me understand integration by parts?"}]
        ),
    )
    assert decision.enqueued
    job_id = decision.job_id

    with patch("memory.jobs.main.evaluate_memory", new=AsyncMock(side_effect=RuntimeError("LLM timeout"))):
        result = process_pending_jobs(batch_size=5)

    assert result.claimed == 1
    assert result.done == 0
    assert result.failed == 1

    with memory_db.get_conn(memory_db_path) as conn:
        row = conn.execute(
            "SELECT status, payload_json FROM memory_update_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        assert row["status"] == "failed"
        payload = json.loads(row["payload_json"])
        assert "LLM timeout" in payload["worker_error"]


# --- per-user LLM config resolution ---


def test_resolve_memory_llm_with_user_config(seed) -> None:
    from app.db import get_conn as app_get_conn
    from tests.mockers import seed_llm_config

    seed(users=["memllm@school.edu"])
    with app_get_conn() as conn:
        user_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("memllm@school.edu",)
        ).fetchone()["id"]
    seed_llm_config(user_id)

    base_url, api_key, model = _resolve_memory_llm(user_id) or ("", "", "")
    assert base_url == "https://api.openai.com/v1"
    assert api_key == "sk-test-key"
    assert model == "gpt-4"


def test_resolve_memory_llm_without_config_returns_none(seed) -> None:
    seed(users=["noconfig@school.edu"])
    from app.db import get_conn as app_get_conn

    with app_get_conn() as conn:
        user_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("noconfig@school.edu",)
        ).fetchone()["id"]
    assert _resolve_memory_llm(user_id) is None


def test_resolve_memory_llm_with_empty_config_returns_none(seed) -> None:
    from app.db import get_conn as app_get_conn
    from app.llmconfig import store
    from app.llmconfig.model import LLMConfig

    seed(users=["emptycfg@school.edu"])
    with app_get_conn() as conn:
        user_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("emptycfg@school.edu",)
        ).fetchone()["id"]
    store.save_config(user_id, LLMConfig(triplets=[]))
    assert _resolve_memory_llm(user_id) is None