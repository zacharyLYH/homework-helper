import json

import pytest

from app.db import get_conn
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
            json={"message": "what is 2+2?", "chat_id": chat_id},
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

    # --- 4. DB metadata includes tools_used ---
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
    assert "tools_used" in meta, f"metadata missing tools_used: {meta}"
    assert meta["tools_used"] == ["calculator"]
    assert meta["model"] == "gpt-4"


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
            json={"message": "Hi", "chat_id": chat_id},
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

    # --- DB has no tools_used in metadata ---
    with get_conn() as conn:
        msgs = conn.execute(
            "SELECT role, content, metadata_json FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()

    assert len(msgs) == 2
    meta = json.loads(msgs[1]["metadata_json"])
    assert "tools_used" not in meta, f"metadata should not contain tools_used: {meta}"
    assert msgs[1]["content"] == "Hello world!"
