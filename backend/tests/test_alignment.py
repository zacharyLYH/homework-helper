import pytest

import app.alignment as alignment
from app.config import settings


def _graph_state(message: str) -> dict:
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content=message)],
        "model": "unknown",
        "pending_tool_calls": 0,
        "pending_tool_calls_data": [],
        "called_tools": [],
        "rejected_reason": "",
        "alignment_score": 0.0,
    }


# ── real-model behavior ──────────────────────────────────────────────


def test_alignment_allows_homework_request():
    """A homework request scores above threshold against the real model."""
    allowed, score, reason = alignment.check_alignment("help me solve this calculus problem")

    assert allowed is True
    assert score >= settings.homework_alignment_threshold
    assert reason == "aligned"


def test_alignment_rejects_off_topic_request():
    allowed, score, reason = alignment.check_alignment("write me a poem about dragons")

    assert allowed is False
    assert score < settings.homework_alignment_threshold
    assert reason == "below_threshold"


def test_alignment_on_topic_scores_higher_than_off_topic():
    _, on_topic_score, _ = alignment.check_alignment("explain how to factor this quadratic equation")
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


# ── graph integration ────────────────────────────────────────────────


async def test_graph_rejects_off_topic_before_agent():
    from app import graph as graph_mod

    result = await graph_mod.compiled_graph.ainvoke(
        _graph_state("write me a poem about dragons"),
        config={"configurable": {"thread_id": "alignment-reject"}},
    )

    assert result["rejected_reason"] == "below_threshold"
    assert len(result["messages"]) == 1, "agent must not run for rejected requests"


async def test_graph_aligned_reaches_agent():
    from app import graph as graph_mod
    from tests.mockers import mock_llm

    with mock_llm(content="Let's break this down"):
        result = await graph_mod.compiled_graph.ainvoke(
            _graph_state("help me solve this calculus problem"),
            config={"configurable": {"thread_id": "alignment-ok"}},
        )

    assert result["rejected_reason"] == ""
    assert len(result["messages"]) == 2, "agent should respond for aligned requests"
