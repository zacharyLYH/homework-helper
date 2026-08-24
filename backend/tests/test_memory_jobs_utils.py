import json

import pytest

from memory import db as memory_db
from memory.jobs.utils import (
    _apply_evaluation,
    _parse_payload,
    _set_job_failed,
    _validate_semantic,
    normalize_concept_key,
)
from memory.schemas import ConceptEdgeUpsert, ConceptStateDelta, ConceptUpsert, MemoryEvaluation


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
        concept_edges=[ConceptEdgeUpsert("one", "two", "related", 0.5), ConceptEdgeUpsert("two", "one", "related", 0.5)],
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
        assert conn.execute("SELECT COUNT(*) FROM learner_observations").fetchone()[0] == 1
        traits = json.loads(conn.execute("SELECT traits_json FROM learner_traits").fetchone()[0])
        assert traits == {"pace": "steady", "topic": "algebra"}
        assert conn.execute("SELECT COUNT(*) FROM concept_edges").fetchone()[0] == 1
        state = conn.execute(
            "SELECT mastery, confidence FROM learner_concept_state"
        ).fetchone()
        assert (state[0], state[1]) == (0.4, 0.8)
        assert conn.execute("SELECT summary FROM memory_summary").fetchone()[0] == "Practice algebra basics."


def test_set_job_failed_preserves_valid_payload_and_raw_invalid_payload(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    with memory_db.get_conn(db_path) as conn:
        conn.execute("INSERT INTO memory_update_jobs (user_id, subject_id, payload_json) VALUES (1, 1, ?)", ("{}",))
        valid_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO memory_update_jobs (user_id, subject_id, payload_json) VALUES (1, 1, ?)", ("bad",))
        invalid_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    _set_job_failed(valid_id, payload_json="{}", error="failure")
    _set_job_failed(invalid_id, payload_json="bad", error="failure")

    with memory_db.get_conn(db_path) as conn:
        valid = json.loads(conn.execute("SELECT payload_json FROM memory_update_jobs WHERE id = ?", (valid_id,)).fetchone()[0])
        invalid = json.loads(conn.execute("SELECT payload_json FROM memory_update_jobs WHERE id = ?", (invalid_id,)).fetchone()[0])
    assert valid["worker_error"] == "failure"
    assert invalid["raw_payload_json"] == "bad"