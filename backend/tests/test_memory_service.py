import json
import sqlite3

from memory import db as memory_db
from memory.service import utils
from memory.service.main import enqueue_memory_update, load_memory_context


def _payload(messages: list[dict[str, str]]) -> dict:
    return {
        "trigger": "chat_turn",
        "memory_loaded": False,
        "memory_context": "",
        "messages": messages,
    }


def test_extract_user_text_filters_roles_and_empty_content() -> None:
    payload = _payload(
        [
            {"role": "assistant", "content": "ignore"},
            {"role": "user", "content": "  first  "},
            {"role": "human", "content": "second"},
            {"role": "user", "content": ""},
            {"role": "user", "content": 123},
            {"role": "user"},
            "invalid",  # type: ignore[list-item]
        ]
    )

    assert utils._extract_user_text(payload) == "first second 123"
    assert utils._extract_user_text(None) == ""
    assert utils._extract_user_text({"messages": "invalid"}) == ""


def test_enqueue_memory_update_skip_decisions(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)

    missing = enqueue_memory_update(
        user_id=None, subject_id=1, chat_id=None, payload=_payload([])
    )
    empty = enqueue_memory_update(
        user_id=1, subject_id=1, chat_id=None, payload=_payload([])
    )
    short = enqueue_memory_update(
        user_id=1,
        subject_id=1,
        chat_id=None,
        payload=_payload([{"role": "user", "content": "too short"}]),
    )

    assert missing.reason == "skipped_missing_scope"
    assert empty.reason == "skipped_no_user_content"
    assert short.reason == "skipped_short_turn"


def test_enqueue_memory_update_deduplicates_and_rate_limits(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)
    payload = _payload([{"role": "user", "content": "a sufficiently long homework turn"}])

    first = enqueue_memory_update(user_id=1, subject_id=1, chat_id=None, payload=payload)
    duplicate = enqueue_memory_update(user_id=1, subject_id=1, chat_id=None, payload=payload)
    assert first.enqueued
    assert duplicate.reason == "skipped_dedup"

    with memory_db.get_conn(db_path) as conn:
        conn.execute("DELETE FROM memory_update_jobs")
        for _ in range(60):
            conn.execute(
                "INSERT INTO memory_update_jobs (user_id, subject_id, status) VALUES (?, ?, 'done')",
                (1, 1),
            )

    limited = enqueue_memory_update(user_id=1, subject_id=1, chat_id=None, payload=payload)
    assert limited.reason == "skipped_rate_limit"


def test_load_memory_context_renders_all_sections_and_logs_trace(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)

    with memory_db.get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO memory_summary (user_id, subject_id, summary) VALUES (1, 2, ?)",
            ("Needs practice",),
        )
        conn.execute(
            "INSERT INTO learner_traits (user_id, subject_id, traits_json) VALUES (1, 2, ?)",
            (json.dumps({"pace": "careful"}),),
        )
        weak_id = conn.execute(
            "INSERT INTO concepts (subject_id, concept_key, display_name) VALUES (2, 'fractions', 'Fractions')"
        ).lastrowid
        prerequisite_id = conn.execute(
            "INSERT INTO concepts (subject_id, concept_key, display_name) VALUES (2, 'arithmetic', 'Arithmetic')"
        ).lastrowid
        conn.execute(
            "INSERT INTO learner_concept_state (user_id, subject_id, concept_id, mastery) VALUES (1, 2, ?, 0.2)",
            (weak_id,),
        )
        conn.execute(
            "INSERT INTO concept_edges (from_concept_id, to_concept_id, relation) VALUES (?, ?, 'prerequisite')",
            (prerequisite_id, weak_id),
        )
        conn.execute(
            "INSERT INTO learner_observations (user_id, subject_id, observation) VALUES (1, 2, 'Misses common denominators')"
        )

    context = load_memory_context(user_id=1, subject_id=2)

    assert "Current summary:" in context.rendered
    assert "Learner traits:" in context.rendered
    assert "Weak concepts:" in context.rendered
    assert "Prerequisites to reinforce:" in context.rendered
    assert "Recent learner observations:" in context.rendered
    assert "Arithmetic" in context.rendered
    assert "Misses common denominators" in context.rendered
    with memory_db.get_conn(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM retrieval_traces").fetchone()[0] == 1


def test_load_memory_context_returns_empty_on_database_error(monkeypatch) -> None:
    class BrokenConnection:
        def __enter__(self):
            raise sqlite3.OperationalError("broken")

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("memory.service.main.get_conn", lambda: BrokenConnection())

    context = load_memory_context(user_id=1, subject_id=2)

    assert context.is_empty
    assert context.rendered == ""