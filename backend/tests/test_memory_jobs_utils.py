import json

import pytest
from memory import db as memory_db
from memory.jobs.utils import (
    _apply_evaluation,
    _claim_next_pending_job,
    _parse_payload,
    _reclaim_stale_running_jobs,
    _set_job_failed,
    _validate_semantic,
    normalize_concept_key,
)
from memory.schemas import (
    ConceptEdgeUpsert,
    ConceptStateDelta,
    ConceptUpsert,
    MemoryEvaluation,
)


def test_normalize_concept_key() -> None:
    assert normalize_concept_key("  Quadratic Formula! ") == "quadratic_formula"
    assert normalize_concept_key("---") == ""
    assert normalize_concept_key("Pythagorean_theorem") == "pythagorean_theorem"


def test_parse_payload_normalizes_missing_and_invalid_message_entries() -> None:
    assert _parse_payload(None)["messages"] == []
    payload = _parse_payload(
        json.dumps(
            {
                "trigger": "chat_turn",
                "memory_loaded": 1,
                "memory_context": None,
                "messages": [{"role": "user", "content": 42}, "invalid"],
            }
        )
    )
    assert payload == {
        "trigger": "chat_turn",
        "memory_loaded": True,
        "memory_context": "None",
        "messages": [{"role": "user", "content": "42"}],
    }
    with pytest.raises(json.JSONDecodeError):
        _parse_payload("not-json")


def test_validate_semantic_applies_all_caps(monkeypatch) -> None:
    monkeypatch.setattr("memory.jobs.utils.MEMORY_LLM_MAX_OBSERVATIONS", 1)
    monkeypatch.setattr("memory.jobs.utils.MEMORY_LLM_MAX_CONCEPTS", 1)
    monkeypatch.setattr("memory.jobs.utils.MEMORY_LLM_MAX_SUMMARY_CHARS", 4)
    evaluation = MemoryEvaluation(
        skip=False,
        observations=["one", "two"],
        concept_upserts=[ConceptUpsert("one", "One"), ConceptUpsert("two", "Two")],
        concept_edges=[
            ConceptEdgeUpsert("one", "two", "related", 0.5),
            ConceptEdgeUpsert("two", "one", "related", 0.5),
        ],
        concept_state_deltas=[],
        trait_updates={},
        updated_summary="12345",
    )

    limited = _validate_semantic(evaluation, job_id=1)

    assert limited.observations == ["one"]
    assert len(limited.concept_upserts) == 1
    assert len(limited.concept_edges) == 1
    assert limited.updated_summary == "1234"


def test_apply_evaluation_writes_and_merges_memory_state(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    with memory_db.get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO concepts (subject_id, concept_key, display_name) VALUES (7, 'existing', 'Existing')"
        )
        conn.execute(
            "INSERT INTO learner_traits (user_id, subject_id, traits_json) VALUES (11, 7, ?)",
            (json.dumps({"pace": "slow"}),),
        )

    evaluation = MemoryEvaluation(
        skip=False,
        observations=["Needs more practice"],
        concept_upserts=[ConceptUpsert("New Concept", "New Concept", ["new"])],
        concept_edges=[ConceptEdgeUpsert("new concept", "existing", "related", 0.7)],
        concept_state_deltas=[ConceptStateDelta("existing", 0.4, 0.8)],
        trait_updates={"pace": "steady", "topic": "algebra"},
        updated_summary="Practice algebra basics.",
    )

    _apply_evaluation(user_id=11, subject_id=7, evaluation=evaluation, job_id=1)

    with memory_db.get_conn(db_path) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM learner_observations").fetchone()[0] == 1
        )
        traits = json.loads(
            conn.execute("SELECT traits_json FROM learner_traits").fetchone()[0]
        )
        assert traits == {"pace": "steady", "topic": "algebra"}
        assert conn.execute("SELECT COUNT(*) FROM concept_edges").fetchone()[0] == 1
        state = conn.execute(
            "SELECT mastery, confidence FROM learner_concept_state"
        ).fetchone()
        assert (state[0], state[1]) == (0.4, 0.8)
        assert (
            conn.execute("SELECT summary FROM memory_summary").fetchone()[0]
            == "Practice algebra basics."
        )


def test_apply_evaluation_skips_unknown_concepts_and_empty_keys(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)

    evaluation = MemoryEvaluation(
        skip=False,
        observations=[],
        concept_upserts=[ConceptUpsert("---", "Dropped")],
        concept_edges=[ConceptEdgeUpsert("missing", "also_missing", "related", 0.5)],
        concept_state_deltas=[ConceptStateDelta("missing", 0.2, 0.3)],
        trait_updates={},
        updated_summary="",
    )

    _apply_evaluation(user_id=1, subject_id=1, evaluation=evaluation, job_id=1)

    with memory_db.get_conn(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM concept_edges").fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM learner_concept_state").fetchone()[0]
            == 0
        )


def test_set_job_failed_preserves_valid_payload_and_raw_invalid_payload(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "memory.db"
    valid_id = None
    invalid_id = None
    valid = None
    invalid = None
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    with memory_db.get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO memory_update_jobs (user_id, subject_id, payload_json) VALUES (1, 1, ?)",
            ("{}",),
        )
        valid_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO memory_update_jobs (user_id, subject_id, payload_json) VALUES (1, 1, ?)",
            ("bad",),
        )
        invalid_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    assert valid_id is not None
    assert invalid_id is not None
    _set_job_failed(valid_id, payload_json="{}", error="failure")
    _set_job_failed(invalid_id, payload_json="bad", error="failure")

    with memory_db.get_conn(db_path) as conn:
        valid = json.loads(
            conn.execute(
                "SELECT payload_json FROM memory_update_jobs WHERE id = ?", (valid_id,)
            ).fetchone()[0]
        )
        invalid = json.loads(
            conn.execute(
                "SELECT payload_json FROM memory_update_jobs WHERE id = ?",
                (invalid_id,),
            ).fetchone()[0]
        )
    assert valid is not None
    assert invalid is not None
    assert valid["worker_error"] == "failure"
    assert invalid["raw_payload_json"] == "bad"


def test_reclaim_stale_running_jobs_resets_only_stale_rows(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    with memory_db.get_conn(db_path) as conn:
        # Stale: claimed long ago, never finished — a dead worker's orphan.
        conn.execute(
            """
            INSERT INTO memory_update_jobs (user_id, subject_id, status, updated_at)
            VALUES (1, 1, 'running', datetime('now', '-1 hour'))
            """
        )
        # Fresh: a live evaluation in a healthy worker.
        conn.execute(
            "INSERT INTO memory_update_jobs (user_id, subject_id, status) VALUES (2, 2, 'running')"
        )

    reclaimed = _reclaim_stale_running_jobs()

    assert reclaimed == 1
    with memory_db.get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT status FROM memory_update_jobs ORDER BY id"
        ).fetchall()
        assert str(rows[0]["status"]) == "pending"  # stale → requeued
        assert str(rows[1]["status"]) == "running"  # fresh → untouched


def test_reclaim_noop_when_no_stale_jobs(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    with memory_db.get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO memory_update_jobs (user_id, subject_id, status) VALUES (1, 1, 'running')"
        )
        conn.execute(
            "INSERT INTO memory_update_jobs (user_id, subject_id, status) VALUES (1, 1, 'pending')"
        )

    assert _reclaim_stale_running_jobs() == 0


def test_claim_next_pending_job_orders_and_transitions(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    with memory_db.get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_update_jobs (user_id, subject_id, status, created_at)
            VALUES (1, 1, 'pending', datetime('now', '-2 seconds'))
            """
        )
        conn.execute(
            "INSERT INTO memory_update_jobs (user_id, subject_id, status) VALUES (1, 1, 'pending')"
        )

    claimed = _claim_next_pending_job()

    assert claimed is not None
    claimed_id = int(claimed["id"])
    with memory_db.get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, status FROM memory_update_jobs ORDER BY id"
        ).fetchall()
        first_id = int(rows[0]["id"])
        assert claimed_id == first_id  # oldest first (created_at, id)
        assert str(rows[0]["status"]) == "running"
        assert str(rows[1]["status"]) == "pending"


def test_set_job_failed_handles_missing_payload(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "memory.db"
    job_id = None
    row = None
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    with memory_db.get_conn(db_path) as conn:
        job_id = conn.execute(
            "INSERT INTO memory_update_jobs (user_id, subject_id) VALUES (1, 1)"
        ).lastrowid

    assert job_id is not None
    _set_job_failed(job_id, payload_json=None, error="failure")

    with memory_db.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT status, payload_json FROM memory_update_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "failed"
    assert json.loads(row["payload_json"]) == {"worker_error": "failure"}
