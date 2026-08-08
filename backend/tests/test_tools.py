import json
from unittest.mock import patch

import httpx
import pytest

from app.db import get_conn, get_debug_conn
from tests.mockers import mock_tool_llm, mock_title_llm


# ── helpers ──────────────────────────────────────────────────────────


def _make_token():
    from app.auth import create_access_token
    from app.db import get_conn as _gc
    from app.schemas import User as _User

    with _gc() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = 'alice@school.edu'").fetchone()
    user = _User(id=row["id"], email=row["email"], created_at=row["created_at"])
    return create_access_token(user)


def _extract_sse(body: str) -> list[dict]:
    return [json.loads(l.removeprefix("data: ")) for l in body.split("\n") if l.strip().startswith("data: ")]


# ── fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def chat(client, seed):
    seed(users=["alice@school.edu"])

    async def _setup():
        await client.post("/api/auth/request-code", json={"email": "alice@school.edu"})
        with get_conn() as conn:
            row = conn.execute(
                "SELECT code FROM verification_codes WHERE email = ?", ("alice@school.edu",)
            ).fetchone()
        await client.post("/api/auth/verify", json={"email": "alice@school.edu", "code": row["code"]})
        sub = await client.post("/api/subjects", params={"name": "Math"})
        chat_resp = await client.post("/api/chats", params={"subject_id": sub.json()["id"], "mode": "guide"})
        return chat_resp.json()["id"]

    return _setup


async def test_list_tools(client):
    resp = await client.get("/api/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    assert any(t["name"] for t in data)


async def test_tool_call_calculator_flow(client, chat):
    """UAT: agent calls calculator → real tool runs → final text streamed.

    Exercises the full ReAct loop:
      agent → tool_executor → agent → end
    with *only* the LLM HTTP transport mocked.  The graph, state reducers,
    calculator tool, DB writes, and SSE event emission are all real code.
    """
    chat_id = await chat()
    token = _make_token()
    tool_args = '{"expression":"2+2"}'

    with mock_tool_llm("calculator", tool_args, "The answer is 4."), mock_title_llm("Test"):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "help me solve this calculus problem", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    events = _extract_sse(resp.text)

    # --- 1. tool_call SSE event emitted ---
    tool_call_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_call_events) == 1, f"Expected 1 tool_call event, got {len(tool_call_events)}"
    tc = tool_call_events[0]
    assert tc["name"] == "calculator"
    assert tc["args"] == {"expression": "2+2"}
    assert tc["id"] is not None

    # --- 2. tokens streamed after tool execution ---
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) > 0
    full = "".join(e["content"] for e in token_events)
    assert full == "The answer is 4.", f"Expected 'The answer is 4.', got {full!r}"

    # --- 3. done event present ---
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assert done_events[0]["model"] == "gpt-4"

    # --- 4. structured logs created ---
    with get_debug_conn() as conn:
        log_rows = conn.execute(
            "SELECT type, message_id, log FROM structured_logs ORDER BY created_at ASC"
        ).fetchall()
        assert len(log_rows) > 0, "Expected structured logs to be created"
        log_types = [r["type"] for r in log_rows]
        assert "chat_request" in log_types
        assert "llm_request" in log_types
        assert "agent_start" in log_types
        assert "chat_response" in log_types
        # tool_executor actually ran (not a no-op)
        assert "tool_result" in log_types, "Expected tool_result log — tool_executor should have executed"
        # No dedup skip (tool was called once, no repeats)
        assert "tool_executor_skip" not in log_types, "tool_executor_skip should not appear for single tool call"
        # message_id should be set on the last log entries (chat_response)
        chat_response_logs = [r for r in log_rows if r["type"] == "chat_response"]
        assert len(chat_response_logs) > 0
        assert chat_response_logs[0]["message_id"] is not None

    # --- 5. DB metadata includes tools_used ---
    with get_conn() as conn:
        msgs = conn.execute(
            "SELECT role, content, metadata_json FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()

    assert len(msgs) == 2, f"Expected 2 messages, got {len(msgs)}"
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "The answer is 4."

    meta = json.loads(msgs[1]["metadata_json"])
    assert meta["model"] == "gpt-4"
    assert "tool_calls" in meta, f"metadata missing tool_calls: {meta}"
    assert meta["tool_calls"] == [{"name": "calculator", "args": {"expression": "2+2"}, "id": "call_mock_tc_001"}], (
        f"Unexpected tool_calls in metadata: {meta['tool_calls']}"
    )


async def test_tool_call_no_tool_needed(client, chat):
    """UAT: plain text — no tool_executor invoked.

    Verifies the conditional edge routes directly to END when the agent
    produces a text response without tool calls.
    """
    chat_id = await chat()
    token = _make_token()

    with mock_tool_llm(None, "", "Hello world!"), mock_title_llm("Test"):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "help me with my homework assignment", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    events = _extract_sse(resp.text)

    # --- no tool_call events ---
    tool_call_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_call_events) == 0, f"Expected 0 tool_call events, got {len(tool_call_events)}"

    # --- tokens streamed ---
    token_events = [e for e in events if e["type"] == "token"]
    full = "".join(e["content"] for e in token_events)
    assert full == "Hello world!"

    # --- structured logs created (no tool flow) ---
    with get_debug_conn() as conn:
        log_rows = conn.execute(
            "SELECT type, message_id FROM structured_logs ORDER BY created_at ASC"
        ).fetchall()
        assert len(log_rows) > 0
        log_types = [r["type"] for r in log_rows]
        assert "chat_request" in log_types
        assert "agent_start" in log_types
        assert "llm_stream_start" in log_types
        assert "chat_response" in log_types
        # No tool_call events since no tools were needed
        assert "tool_call" not in log_types

    # --- DB has no tools_used in metadata ---
    with get_conn() as conn:
        msgs = conn.execute(
            "SELECT role, content, metadata_json FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()

    assert len(msgs) == 2
    meta = json.loads(msgs[1]["metadata_json"])
    assert "tool_calls" not in meta, f"metadata should not contain tool_calls: {meta}"
    assert msgs[1]["content"] == "Hello world!"


async def test_whiteboard_create_diagram_emits_drawing_event(client, chat):
    """UAT: create_diagram tool → drawing SSE event emitted, no JSON in reply text.

    Verifies the whiteboard interception: the tool's element payload is
    streamed as a `drawing` event (for the canvas) and is NOT included in
    the assistant's text reply (no illegible JSON on the FE).
    """
    chat_id = await chat()
    token = _make_token()
    tool_args = json.dumps({
        "nodes": [
            {"id": "a", "label": "Start", "kind": "box"},
            {"id": "b", "label": "End", "kind": "box"},
        ],
        "edges": [{"from_id": "a", "to_id": "b", "label": "next", "directed": True}],
    })

    with mock_tool_llm("create_diagram", tool_args, "Here is the flow diagram."), mock_title_llm("Test"):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "help me draw a diagram for my homework", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    events = _extract_sse(resp.text)

    # --- 1. drawing SSE event emitted with elements ---
    drawing_events = [e for e in events if e["type"] == "drawing"]
    assert len(drawing_events) == 1, f"Expected 1 drawing event, got {len(drawing_events)}"
    elements = drawing_events[0]["elements"]
    assert isinstance(elements, list) and len(elements) >= 2, f"Expected >=2 elements, got {len(elements)}"
    # 2 rect nodes + 1 arrow edge
    assert sum(1 for e in elements if e["type"] == "rect") == 2
    assert sum(1 for e in elements if e["type"] == "arrow") == 1

    # --- 2. tool_call event present ---
    tool_call_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_call_events) == 1
    assert tool_call_events[0]["name"] == "create_diagram"

    # --- 3. reply text is clean prose — no JSON leaked ---
    token_events = [e for e in events if e["type"] == "token"]
    full = "".join(e["content"] for e in token_events)
    assert full == "Here is the flow diagram.", f"Expected clean prose, got {full!r}"
    assert '"type"' not in full, "JSON element payload leaked into reply text"

    # --- 4. done event present ---
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1

    # --- 5. drawing elements persisted in drawing_json column (survives refresh) ---
    with get_conn() as conn:
        msgs = conn.execute(
            "SELECT role, content, metadata_json, drawing_json FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()

    assert len(msgs) == 2
    persisted = json.loads(msgs[1]["drawing_json"]) if msgs[1]["drawing_json"] else None
    assert isinstance(persisted, list) and len(persisted) >= 2, f"Expected persisted drawing, got {persisted!r}"
    assert sum(1 for e in persisted if e["type"] == "rect") == 2
    assert sum(1 for e in persisted if e["type"] == "arrow") == 1
    meta = json.loads(msgs[1]["metadata_json"])
    assert "drawing" not in meta, f"drawing should not live in metadata_json: {meta}"


async def test_duplicate_tool_call_prevention(client, chat):
    """UAT: LLM keeps calling the same tool+args → dedup prevents infinite loop.

    Uses a custom mock that returns calculator tool calls on EVERY LLM
    request (simulating a stuck LLM).  The called_tools dedup should:
      - execute the tool exactly once
      - skip the repeat call
      - end the graph without looping (≤3 LLM calls)
    """
    chat_id = await chat()
    token = _make_token()

    call_count = [0]

    async def _handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        body = await request.aread()
        req = json.loads(body) if body else {}
        is_stream = req.get("stream", False)

        if not is_stream:
            return httpx.Response(200, json={
                "id": "chatcmpl-mock", "object": "chat.completion",
                "created": 1677652288, "model": "gpt-4",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": ""},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35},
            })

        async def _sse_body():
            """Always return calculator tool call chunks."""
            yield _sse(json.dumps({
                "id": "chatcmpl-mock", "object": "chat.completion.chunk",
                "created": 1677652288, "model": "gpt-4",
                "choices": [{
                    "index": 0,
                    "delta": {"tool_calls": [{"index": 0, "id": "call_mock_tc_001",
                                              "type": "function",
                                              "function": {"name": "calculator", "arguments": ""}}]},
                    "finish_reason": None,
                }],
            }))
            yield _sse(json.dumps({
                "id": "chatcmpl-mock", "object": "chat.completion.chunk",
                "created": 1677652288, "model": "gpt-4",
                "choices": [{
                    "index": 0,
                    "delta": {"tool_calls": [{"index": 0,
                                              "function": {"arguments": '{"expression":"2+2"}'}}]},
                    "finish_reason": None,
                }],
            }))
            yield _sse(json.dumps({
                "id": "chatcmpl-mock", "object": "chat.completion.chunk",
                "created": 1677652288, "model": "gpt-4",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
            }))
            yield b"data: [DONE]\n\n"

        return httpx.Response(
            200, content=_sse_body(),
            headers={"Content-Type": "text/event-stream"},
        )

    def _sse(data: str) -> bytes:
        return f"data: {data}\n\n".encode()

    transport = httpx.MockTransport(_handler)
    mock_client = httpx.AsyncClient(transport=transport)

    with patch(
        "langchain_openai.chat_models.base._get_default_async_httpx_client",
        return_value=mock_client,
    ), mock_title_llm("Test"):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "help me solve this calculus problem", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    events = _extract_sse(resp.text)

    # --- 1. tool_call SSE events ---
    # LLM calls the tool in both agent iterations before dedup stops the loop
    tool_call_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_call_events) == 2, (
        f"Expected 2 tool_call events (LLM called tool twice), got {len(tool_call_events)}"
    )
    for tc in tool_call_events:
        assert tc["name"] == "calculator"
        assert tc["args"] == {"expression": "2+2"}

    # --- 2. done event present ---
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1, f"Expected 1 done event, got {len(done_events)}"

    # --- 3. LLM not called excessively ---
    assert call_count[0] <= 3, (
        f"LLM called {call_count[0]} times — infinite loop not prevented"
    )

    # --- 4. structured logs confirm one execution + one skip ---
    with get_debug_conn() as conn:
        log_rows = conn.execute(
            "SELECT type, log FROM structured_logs ORDER BY created_at ASC"
        ).fetchall()
    log_types = [r["type"] for r in log_rows]

    tool_results = [t for t in log_types if t == "tool_result"]
    assert len(tool_results) == 1, (
        f"Expected 1 tool_result (tool executed once), got {len(tool_results)}"
    )

    # Dedup happens in the edge function (routes to END instead of tool_executor)
    graph_route_skip_logs = [
        r for r in log_rows
        if r["type"] == "graph_route" and json.loads(r["log"]).get("reason") == "all_tools_already_called"
    ]
    assert len(graph_route_skip_logs) == 1, (
        "Expected graph_route log with reason=all_tools_already_called — "
        "edge function should have broken the loop"
    )

    # --- 5. assistant message saved (empty content since no text was generated) ---
    with get_conn() as conn:
        msgs = conn.execute(
            "SELECT role, content, metadata_json FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()

    assert len(msgs) == 2, f"Expected 2 messages, got {len(msgs)}"
    assert msgs[1]["role"] == "assistant"
    meta = json.loads(msgs[1]["metadata_json"])
    assert "tool_calls" in meta, f"metadata missing tool_calls: {meta}"
    assert len(meta["tool_calls"]) == 2, (
        f"Expected 2 tool_calls entries (both LLM calls recorded), got {len(meta['tool_calls'])}"
    )
    for tc in meta["tool_calls"]:
        assert tc["name"] == "calculator"
        assert tc["args"] == {"expression": "2+2"}
