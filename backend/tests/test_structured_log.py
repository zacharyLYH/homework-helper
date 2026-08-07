import json
from datetime import datetime, timezone

import pytest

import app.structured_log as sl
from app.db import get_debug_conn


@pytest.fixture(autouse=True)
def _reset_logger_var():
    yield
    sl._logger_var.set(None)


def _fetch_logs():
    with get_debug_conn() as conn:
        rows = conn.execute(
            "SELECT type, message_id, log, _req_id FROM structured_logs ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


async def _dummy_receive():
    return {"type": "http.request", "body": b""}


async def _dummy_send(_):
    return None


def _http_scope():
    return {"type": "http", "method": "GET", "path": "/test", "headers": []}


async def _run_request(app, *, pct, monkeypatch, scope=None):
    monkeypatch.setattr("app.config.settings.structured_logging_pct", pct)
    middleware = sl.StructuredTraceMiddleware(app)
    await middleware(scope or _http_scope(), _dummy_receive, _dummy_send)


# --- StructuredLogger unit tests ---


def test_buffers_events_until_commit():
    logger = sl.StructuredLogger(should_commit=True)
    logger.log("chat_request", prompt="help")
    logger.log("chat_response", tokens=42)

    assert len(_fetch_logs()) == 0

    logger.commit()

    rows = _fetch_logs()
    assert len(rows) == 2
    assert [r["type"] for r in rows] == ["chat_request", "chat_response"]
    assert {r["_req_id"] for r in rows} == {logger._req_id}
    assert json.loads(rows[0]["log"]) == {"prompt": "help"}
    assert json.loads(rows[1]["log"]) == {"tokens": 42}


def test_unsampled_logger_discards_events():
    logger = sl.StructuredLogger(should_commit=False)
    logger.log("chat_request", prompt="help")
    logger.commit()

    assert _fetch_logs() == []


def test_commit_without_entries_is_noop():
    logger = sl.StructuredLogger(should_commit=True)
    logger.commit()

    assert _fetch_logs() == []


def test_commit_is_idempotent():
    logger = sl.StructuredLogger(should_commit=True)
    logger.log("chat_request")
    logger.commit()
    logger.commit()

    assert len(_fetch_logs()) == 1


def test_force_creates_committing_logger_when_none():
    assert sl.get_structured_logger() is None

    sl.force_structured_logger()

    logger = sl.get_structured_logger()
    assert logger is not None
    assert logger.should_commit is True


def test_force_flips_unsampled_logger_to_commit():
    logger = sl.StructuredLogger(should_commit=False)
    sl._logger_var.set(logger)

    sl.force_structured_logger()
    logger.log("chat_rejected", reason="below_threshold")
    logger.commit()

    assert logger.should_commit is True
    assert len(_fetch_logs()) == 1


def test_structured_log_is_noop_without_logger():
    sl.structured_log("chat_request", prompt="help")

    assert _fetch_logs() == []


def test_message_id_stamped_on_all_buffered_entries():
    logger = sl.StructuredLogger(should_commit=True)
    logger.log("chat_request")
    logger.set_message_id(7)
    logger.log("chat_response")
    logger.commit()

    rows = _fetch_logs()
    assert len(rows) == 2
    assert all(r["message_id"] == 7 for r in rows)


def test_message_id_none_when_unset():
    logger = sl.StructuredLogger(should_commit=True)
    logger.log("chat_request")
    logger.commit()

    assert _fetch_logs()[0]["message_id"] is None


def test_log_serializes_non_json_data():
    logger = sl.StructuredLogger(should_commit=True)
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    logger.log("chat_request", when=ts, nested={"a": 1})
    logger.commit()

    parsed = json.loads(_fetch_logs()[0]["log"])
    assert parsed == {"when": str(ts), "nested": {"a": 1}}


# --- Middleware tests ---


async def test_middleware_commits_sampled_request(monkeypatch):
    async def app(scope, receive, send):
        sl.structured_log("chat_request", prompt="help")
        sl.structured_log("chat_response", tokens=42)

    await _run_request(app, pct=100, monkeypatch=monkeypatch)

    rows = _fetch_logs()
    assert [r["type"] for r in rows] == ["chat_request", "chat_response"]
    assert len({r["_req_id"] for r in rows}) == 1


async def test_middleware_discards_unsampled_request(monkeypatch):
    async def app(scope, receive, send):
        sl.structured_log("chat_request", prompt="help")

    await _run_request(app, pct=0, monkeypatch=monkeypatch)

    assert _fetch_logs() == []


async def test_middleware_force_commits_unsampled_request(monkeypatch):
    async def app(scope, receive, send):
        sl.structured_log("chat_request", prompt="help")
        sl.force_structured_logger()
        sl.structured_log("chat_rejected", reason="below_threshold")

    await _run_request(app, pct=0, monkeypatch=monkeypatch)

    rows = _fetch_logs()
    assert [r["type"] for r in rows] == ["chat_request", "chat_rejected"]


async def test_middleware_passes_through_non_http_scope(monkeypatch):
    async def app(scope, receive, send):
        sl.structured_log("chat_request", prompt="help")

    await _run_request(app, pct=100, monkeypatch=monkeypatch, scope={"type": "websocket"})

    assert sl.get_structured_logger() is None
    assert _fetch_logs() == []


async def test_middleware_resets_logger_after_request(monkeypatch):
    async def app(scope, receive, send):
        assert sl.get_structured_logger() is not None

    await _run_request(app, pct=100, monkeypatch=monkeypatch)

    assert sl.get_structured_logger() is None


async def test_middleware_uses_single_req_id_per_request(monkeypatch):
    seen = []

    async def app(scope, receive, send):
        logger = sl.get_structured_logger()
        assert logger is not None
        seen.append(logger._req_id)

    await _run_request(app, pct=100, monkeypatch=monkeypatch)
    await _run_request(app, pct=100, monkeypatch=monkeypatch)

    assert len(seen) == 2
    assert seen[0] != seen[1]
