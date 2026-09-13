import threading

import pytest

import app.alignment as alignment
from app.config import settings


def _graph_state(message: str, user_id: int = 1) -> dict:
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content=message)],
        "model": "unknown",
        "pending_tool_calls": 0,
        "pending_tool_calls_data": [],
        "called_tools": [],
        "user_id": user_id,
        "subject_id": None,
        "memory_context": "",
        "memory_loaded": False,
        "memory_enabled": False,
        "rejected_reason": "",
        "alignment_score": 0.0,
    }


# ── real-model behavior ──────────────────────────────────────────────


def test_alignment_allows_homework_request():
    """A homework request scores above threshold against the real model."""
    allowed, score, reason = alignment.check_alignment(
        "help me solve this calculus problem"
    )

    assert allowed is True
    assert score >= settings.homework_alignment_threshold
    assert reason == "aligned"


def test_alignment_rejects_off_topic_request():
    allowed, score, reason = alignment.check_alignment("write me a poem about dragons")

    assert allowed is False
    assert score < settings.homework_alignment_threshold
    assert reason == "below_threshold"


def test_alignment_on_topic_scores_higher_than_off_topic():
    _, on_topic_score, _ = alignment.check_alignment(
        "explain how to factor this quadratic equation"
    )
    _, off_topic_score, _ = alignment.check_alignment("recommend a good movie")

    assert on_topic_score > off_topic_score


def test_alignment_empty_message_rejected():
    allowed, score, reason = alignment.check_alignment("   ")

    assert allowed is False
    assert score == 0.0
    assert reason == "below_threshold"


def test_alignment_fails_closed_on_encoder_error(monkeypatch):
    """A broken model path must reject rather than pass through unchecked."""
    bad_encoder = alignment.HuggingFaceEncoder(name="/nonexistent/model/path")
    monkeypatch.setattr(alignment, "_encoder", bad_encoder)
    monkeypatch.setattr(alignment, "_corpus_embeddings", None)

    allowed, score, reason = alignment.check_alignment("help me with my homework")

    assert allowed is False
    assert score == 0.0
    assert reason == "encoder_unavailable"


def test_encoder_concurrent_encode_single_load():
    """Concurrent cold-start encode() calls share one model load, no crash.

    Regression for the backend crash seen when several first chat turns hit
    `check_alignment` at once (LangGraph runs the sync node in a thread
    executor, so `encode` races from multiple threads).
    """
    enc = alignment.HuggingFaceEncoder(name=settings.embedding_model)
    n_threads = 8
    errors: list[Exception] = []

    def run() -> None:
        try:
            vecs = enc.encode(["help me with my homework"])
            assert len(vecs) == 1 and len(vecs[0]) == 384
        except Exception as e:  # pragma: no cover - only on regression
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert enc.is_loaded()


def test_encoder_warmup_idempotent_and_fail_soft(monkeypatch):
    """warmup() is idempotent, thread-safe, and returns False on failure."""
    enc = alignment.HuggingFaceEncoder(name=settings.embedding_model)

    assert enc.is_loaded() is False
    assert enc.warmup() is True
    assert enc.is_loaded() is True
    assert enc.warmup() is True  # second call is a no-op

    broken = alignment.HuggingFaceEncoder(name="/nonexistent/model/path")
    assert broken.warmup() is False
    assert broken.is_loaded() is False


def test_alignment_check_alignment_concurrent_real_model():
    """Concurrent check_alignment calls against the real model all succeed."""
    n_threads = 6
    results: list[tuple[bool, float, str]] = []
    errors: list[Exception] = []

    def run(i: int) -> None:
        try:
            msg = (
                "help me solve this calculus problem"
                if i % 2 == 0
                else "recommend a good movie"
            )
            results.append(alignment.check_alignment(msg))
        except Exception as e:  # pragma: no cover - only on regression
            errors.append(e)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(results) == n_threads
    assert all(reason == "aligned" for allowed, _, reason in results[::2])
    assert all(reason == "below_threshold" for allowed, _, reason in results[1::2])


# ── graph integration ────────────────────────────────────────────────


async def test_graph_rejects_off_topic_before_agent():
    from app import graph as graph_mod

    result = await graph_mod.compiled_graph.ainvoke(
        _graph_state("write me a poem about dragons"),
        config={"configurable": {"thread_id": "alignment-reject"}},
    )

    assert result["rejected_reason"] == "below_threshold"
    assert len(result["messages"]) == 1, "agent must not run for rejected requests"


async def test_graph_aligned_reaches_agent(setup_test_db):
    from app import graph as graph_mod
    from app.db import get_conn
    from tests.mockers import mock_llm, seed_llm_config

    with get_conn() as conn:
        conn.execute("INSERT INTO users (email) VALUES ('alice@school.edu')")
        row = conn.execute(
            "SELECT id FROM users WHERE email = 'alice@school.edu'"
        ).fetchone()
    user_id = row["id"]
    seed_llm_config(user_id)

    with mock_llm(content="Let's break this down"):
        result = await graph_mod.compiled_graph.ainvoke(
            _graph_state("help me solve this calculus problem", user_id=user_id),
            config={"configurable": {"thread_id": "alignment-ok"}},
        )

    assert result["rejected_reason"] == ""
    assert len(result["messages"]) == 2, "agent should respond for aligned requests"
