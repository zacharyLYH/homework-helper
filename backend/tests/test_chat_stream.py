import asyncio
import json
from collections.abc import AsyncGenerator
from unittest.mock import patch

import httpx
import pytest

from app.db import get_conn
from tests.mockers import mock_llm, mock_title_llm


# ── helpers ──────────────────────────────────────────────────────────


def _make_token():
    from app.auth import create_access_token
    from app.db import get_conn as _gc
    from app.schemas import User as _User

    with _gc() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = 'alice@school.edu'").fetchone()
    user = _User(id=row["id"], email=row["email"], created_at=row["created_at"])
    return create_access_token(user)


def _sse(data: str) -> bytes:
    return f"data: {data}\n\n".encode()


def _chunk_event(content: str) -> str:
    return json.dumps({
        "id": "chatcmpl-mock",
        "object": "chat.completion.chunk",
        "created": 1677652288,
        "model": "gpt-4",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    })


def _finish_event() -> str:
    return json.dumps({
        "id": "chatcmpl-mock",
        "object": "chat.completion.chunk",
        "created": 1677652288,
        "model": "gpt-4",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20},
    })


def _sse_stream(words: list[str]) -> AsyncGenerator[bytes, None]:
    async def _body():
        for word in words:
            yield _sse(_chunk_event(word))
        yield _sse(_finish_event())
        yield b"data: [DONE]\n\n"

    return _body()


async def _save_config_for_alice(cfg) -> int:
    from app.db import get_conn as _gc

    with _gc() as conn:
        user_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("alice@school.edu",)
        ).fetchone()["id"]
    from app.llmconfig import store

    store.save_config(user_id, cfg)
    return user_id


async def _setup_chat_session(client) -> int:
    await client.post("/api/auth/request-code", json={"email": "alice@school.edu"})
    with get_conn() as conn:
        row = conn.execute(
            "SELECT code FROM verification_codes WHERE email = ?", ("alice@school.edu",)
        ).fetchone()
        code = row["code"]
    await client.post("/api/auth/verify", json={"email": "alice@school.edu", "code": code})
    subject_resp = await client.post("/api/subjects", params={"name": "Math"})
    subject_id = subject_resp.json()["id"]
    chat_resp = await client.post("/api/chats", params={"subject_id": subject_id})
    return chat_resp.json()["id"]


@pytest.fixture
def auth_and_chat(client, seed):
    seed(users=["alice@school.edu"])
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE email = 'alice@school.edu'"
        ).fetchone()
    from tests.mockers import seed_llm_config
    seed_llm_config(row["id"])

    async def _setup():
        return await _setup_chat_session(client)

    return _setup


@pytest.fixture
def auth_and_chat_no_config(client, seed):
    seed(users=["alice@school.edu"])

    async def _setup():
        return await _setup_chat_session(client)

    return _setup


def _error_lines(body: str):
    lines = [l for l in body.split("\n") if l.strip()]
    return [l for l in lines if '"type": "error"' in l]


# ── happy path (existing) ────────────────────────────────────────────


async def test_chat_stream_events(client, auth_and_chat):
    chat_id = await auth_and_chat()
    token = _make_token()

    with mock_llm(content="Hello world"), mock_title_llm("Test Title"):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "help me solve this calculus problem", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.text

    assert resp.status_code == 200
    lines = [l for l in body.split("\n") if l.strip()]

    token_lines = [l for l in lines if '"type": "token"' in l]
    assert len(token_lines) == 2
    assert json.loads(token_lines[0].removeprefix("data: "))["content"] == "Hello "
    assert json.loads(token_lines[1].removeprefix("data: "))["content"] == "world"

    done_line = next(l for l in lines if '"type": "done"' in l)
    done_data = json.loads(done_line.removeprefix("data: "))
    assert done_data["model"] == "gpt-4"
    assert done_data["usage"]["total_tokens"] == 20

    with get_conn() as conn:
        messages = conn.execute(
            "SELECT role, content, token_count FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()
        assert len(messages) == 2
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hello world"
        assert messages[1]["token_count"] == 20

        chat = conn.execute(
            "SELECT total_tokens, input_tokens, output_tokens FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        assert chat["total_tokens"] == 20


# ── sad paths ────────────────────────────────────────────────────────


async def test_chat_stream_no_auth(client, auth_and_chat):
    chat_id = await auth_and_chat()
    client.cookies.clear()

    resp = await client.post(
        "/api/chat/stream",
        json={"message": "Hello", "chat_id": chat_id},
    )

    assert resp.status_code == 401


async def test_chat_stream_empty_message(client, auth_and_chat):
    chat_id = await auth_and_chat()
    token = _make_token()

    with mock_llm(content="Hello"), mock_title_llm("Test Title"):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200


# ── edge cases ───────────────────────────────────────────────────────


async def test_chat_stream_with_image(client, auth_and_chat):
    chat_id = await auth_and_chat()
    token = _make_token()
    image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    with mock_llm(content="Image received"), mock_title_llm("Test Title"):
        resp = await client.post(
            "/api/chat/stream",
            json={
                "message": "What is this diagram from my physics homework?",
                "chat_id": chat_id,
                "image": image_b64,
                "image_media_type": "image/png",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.text

    assert resp.status_code == 200
    lines = [l for l in body.split("\n") if l.strip()]

    token_lines = [l for l in lines if '"type": "token"' in l]
    assert len(token_lines) == 2
    assert json.loads(token_lines[0].removeprefix("data: "))["content"] == "Image "
    assert json.loads(token_lines[1].removeprefix("data: "))["content"] == "received"

    with get_conn() as conn:
        msgs = conn.execute(
            "SELECT role, content, image_base64, image_media_type FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()

    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "What is this diagram from my physics homework?"
    assert msgs[0]["image_base64"] == image_b64
    assert msgs[0]["image_media_type"] == "image/png"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "Image received"


async def test_chat_stream_second_message(client, auth_and_chat):
    """Send two consecutive messages — graph loads full message history."""
    chat_id = await auth_and_chat()
    token = _make_token()

    with mock_llm(content="First reply"), mock_title_llm("Test Title"):
        resp1 = await client.post(
            "/api/chat/stream",
            json={"message": "Help me with my first homework question", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp1.status_code == 200

    with mock_llm(content="Second reply"), mock_title_llm():
        resp2 = await client.post(
            "/api/chat/stream",
            json={"message": "Help me with my second homework question", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp2.status_code == 200

    with get_conn() as conn:
        msgs = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()

    assert len(msgs) == 4
    assert [dict(r) for r in msgs] == [
        {"role": "user", "content": "Help me with my first homework question"},
        {"role": "assistant", "content": "First reply"},
        {"role": "user", "content": "Help me with my second homework question"},
        {"role": "assistant", "content": "Second reply"},
    ]

    lines = [l for l in resp2.text.split("\n") if l.strip()]
    token_lines = [l for l in lines if '"type": "token"' in l]
    full = "".join(json.loads(l.removeprefix("data: "))["content"] for l in token_lines)
    assert full == "Second reply"


# ── alignment gate ───────────────────────────────────────────────────


async def test_chat_stream_rejects_off_topic_message(client, auth_and_chat, monkeypatch):
    chat_id = await auth_and_chat()
    token = _make_token()

    monkeypatch.setattr("app.graph.check_alignment", lambda _text: (False, 0.01, "below_threshold"))

    resp = await client.post(
        "/api/chat/stream",
        json={"message": "write me a poem about dragons", "chat_id": chat_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    lines = [l for l in resp.text.split("\n") if l.strip()]

    token_lines = [l for l in lines if '"type": "token"' in l]
    full = "".join(json.loads(l.removeprefix("data: "))["content"] for l in token_lines)
    assert "homework" in full

    done_line = next(l for l in lines if '"type": "done"' in l)
    done_data = json.loads(done_line.removeprefix("data: "))
    assert done_data["usage"]["total_tokens"] == 0

    with get_conn() as conn:
        msgs = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()
    assert msgs == [], "rejected bad data must not be persisted"


async def test_chat_stream_rejection_is_structured_logged(client, auth_and_chat, monkeypatch):
    chat_id = await auth_and_chat()
    token = _make_token()

    monkeypatch.setattr("app.graph.check_alignment", lambda _text: (False, 0.01, "below_threshold"))

    resp = await client.post(
        "/api/chat/stream",
        json={"message": "tell me a joke", "chat_id": chat_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    import sqlite3

    from app.db import DEBUG_DB_PATH

    conn = sqlite3.connect(DEBUG_DB_PATH)
    try:
        rows = conn.execute(
            "SELECT type, log FROM structured_logs WHERE type = 'chat_rejected'"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    assert "tell me a joke" in rows[0][1]
    assert '"reason": "below_threshold"' in rows[0][1]
    assert '"score":' in rows[0][1]


async def test_chat_stream_allows_aligned_message(client, auth_and_chat):
    chat_id = await auth_and_chat()
    token = _make_token()

    with mock_llm(content="Hello world"), mock_title_llm("Test Title"):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "help me with my calculus homework", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    lines = [l for l in resp.text.split("\n") if l.strip()]
    token_lines = [l for l in lines if '"type": "token"' in l]
    full = "".join(json.loads(l.removeprefix("data: "))["content"] for l in token_lines)
    assert full == "Hello world"

    with get_conn() as conn:
        msgs = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()
    assert len(msgs) == 2
    assert msgs[0]["content"] == "help me with my calculus homework"
    assert msgs[1]["content"] == "Hello world"


async def test_title_and_graph_run_concurrently(client, auth_and_chat):
    """Title generation and graph execution must overlap, not run serially."""
    chat_id = await auth_and_chat()
    token = _make_token()
    order: list[str] = []

    def _sse(data: str) -> bytes:
        return f"data: {data}\n\n".encode()

    async def _llm_handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        req = json.loads(body) if body else {}
        if not req.get("stream", False):
            return httpx.Response(200, json={
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": 1677652288,
                "model": "gpt-4",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello world"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20},
            })

        order.append("graph_started")

        async def _sse_body():
            for word in ["Hello ", "world"]:
                yield _sse(json.dumps({
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "created": 1677652288,
                    "model": "gpt-4",
                    "choices": [{"index": 0, "delta": {"content": word}, "finish_reason": None}],
                }))
            yield _sse(json.dumps({
                "id": "chatcmpl-mock",
                "object": "chat.completion.chunk",
                "created": 1677652288,
                "model": "gpt-4",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20},
            }))
            yield b"data: [DONE]\n\n"

        return httpx.Response(200, content=_sse_body(), headers={"Content-Type": "text/event-stream"})

    class _TitleMock:
        async def __call__(self, chat_id, user_id):
            order.append("title_started")
            await asyncio.sleep(0.2)
            order.append("title_ended")
            yield "Concurrent Title"

    transport = httpx.MockTransport(_llm_handler)
    mock_client = httpx.AsyncClient(transport=transport)

    with patch("langchain_openai.chat_models.base._get_default_async_httpx_client", return_value=mock_client), \
         patch("app.routes.chat.generate_title_stream", _TitleMock()):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "help me with my calculus homework", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert order.index("graph_started") < order.index("title_ended"), \
        "graph must start while title generation is still in flight"

    lines = [l for l in resp.text.split("\n") if l.strip()]
    title_idx = next(i for i, l in enumerate(lines) if '"type": "title"' in l)
    token_idx = next(i for i, l in enumerate(lines) if '"type": "token"' in l)
    assert title_idx < token_idx


# ── quote field ──────────────────────────────────────────────────────


async def test_chat_stream_with_quote(client, auth_and_chat):
    """Quote field is accepted, not stored in DB, and doesn't break streaming."""
    chat_id = await auth_and_chat()
    token = _make_token()

    with mock_llm(content="Here is the refined explanation."), mock_title_llm("Test Title"):
        resp = await client.post(
            "/api/chat/stream",
            json={
                "message": "Can you explain this homework problem more clearly?",
                "chat_id": chat_id,
                "quote": "The quadratic formula is x = (-b ± √(b² - 4ac)) / 2a",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.text

    assert resp.status_code == 200
    lines = [l for l in body.split("\n") if l.strip()]

    token_lines = [l for l in lines if '"type": "token"' in l]
    assert len(token_lines) > 0

    full = "".join(json.loads(l.removeprefix("data: "))["content"] for l in token_lines)
    assert full == "Here is the refined explanation."

    done_line = next(l for l in lines if '"type": "done"' in l)
    done_data = json.loads(done_line.removeprefix("data: "))
    assert done_data["usage"]["total_tokens"] == 20

    with get_conn() as conn:
        msgs = conn.execute(
            "SELECT role, content, quote FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()

    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Can you explain this homework problem more clearly?"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "Here is the refined explanation."

    # Verify quote is stored in its own column (not in metadata_json)
    assert msgs[0]["quote"] == "The quadratic formula is x = (-b ± √(b² - 4ac)) / 2a"
    assert msgs[1]["quote"] is None

    with get_conn() as conn:
        cols = [d["name"] for d in conn.execute("PRAGMA table_info(messages)").fetchall()]
    assert "quote" in cols, "quote should exist as a column in messages table"


async def test_chat_stream_quote_empty_string(client, auth_and_chat):
    """Empty quote string is accepted gracefully."""
    chat_id = await auth_and_chat()
    token = _make_token()

    with mock_llm(content="Hello"), mock_title_llm("Test Title"):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "help me solve this calculus problem", "chat_id": chat_id, "quote": ""},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200


async def test_build_lc_messages_appends_quote_to_last_user_message(setup_test_db):
    """Quote is appended to the last user message, not the system prompt."""
    from app.routes.chat import _build_lc_messages as build
    from app.schemas import ChatRequest

    req = ChatRequest(
        message="what is hex",
        quote="Binary uses 0 and 1.",
        messages=[
            {"role": "user", "content": "what is binary code"},
            {"role": "assistant", "content": "Binary code is a system..."},
            {"role": "user", "content": "what is hex"},
        ],
    )
    msgs = build(req)
    users = [m for m in msgs if m.type == "human"]
    assert len(users) >= 1
    last_user = users[-1]
    assert "Binary uses 0 and 1." in last_user.content
    assert '[quoting: "Binary uses 0 and 1."]' in last_user.content
    assert last_user.content.startswith("what is hex")

    # Verify system msg (GraphState prepends it separately) is untouched
    sys_msgs = [m for m in msgs if m.type == "system"]
    assert not sys_msgs


async def test_build_lc_messages_appends_quote_without_history(setup_test_db):
    """Quote is appended even when no messages history is provided."""
    from app.routes.chat import _build_lc_messages as build
    from app.schemas import ChatRequest

    req = ChatRequest(message="what did you mean?", quote="Some text to quote.")
    msgs = build(req)
    assert len(msgs) == 1
    assert msgs[0].type == "human"
    assert "[quoting: \"Some text to quote.\"]" in msgs[0].content
    assert msgs[0].content.startswith("what did you mean?")


async def test_build_lc_messages_quote_empty_string_skips_append(setup_test_db):
    """Empty quote should not append anything."""
    from app.routes.chat import _build_lc_messages as build
    from app.schemas import ChatRequest

    req = ChatRequest(message="hello", quote="")
    msgs = build(req)
    assert len(msgs) == 1
    assert msgs[0].content == "hello"


async def test_build_lc_messages_quote_none_skips_append(setup_test_db):
    """None quote should not append anything."""
    from app.routes.chat import _build_lc_messages as build
    from app.schemas import ChatRequest

    req = ChatRequest(message="hello")
    msgs = build(req)
    assert len(msgs) == 1
    assert msgs[0].content == "hello"


async def test_build_lc_messages_attaches_image_with_history(setup_test_db):
    """Image reaches the model even when conversation history is provided.

    Regression: with `messages` context present, the previous branch only
    mapped text content and silently dropped req.image, so the LLM never saw
    attached drawings/photos sent from the chat UI.
    """
    from app.routes.chat import _build_lc_messages as build
    from app.schemas import ChatRequest

    req = ChatRequest(
        message="help me factor the equation",
        image="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        image_media_type="image/png",
        messages=[
            {"role": "user", "content": "what is binary code"},
            {"role": "assistant", "content": "Binary code is a system..."},
            {"role": "user", "content": "help me factor the equation"},
        ],
    )
    msgs = build(req)
    assert len(msgs) == 3
    last = msgs[-1]
    assert last.type == "human"
    assert isinstance(last.content, list)
    kinds = {part.get("type") for part in last.content}
    assert kinds == {"image_url", "text"}
    image_part = next(p for p in last.content if p["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    text_part = next(p for p in last.content if p["type"] == "text")
    assert text_part["text"] == "help me factor the equation"
    # Earlier user/assistant messages remain plain text.
    assert msgs[0].content == "what is binary code"
    assert msgs[1].content == "Binary code is a system..."


# ── settings / LLM routing in the chat loop ─────────────────────────


async def test_chat_stream_no_config_streams_error(client, auth_and_chat_no_config):
    """A user with no LLM config gets a graceful error event, not a crash."""
    chat_id = await auth_and_chat_no_config()
    token = _make_token()

    resp = await client.post(
        "/api/chat/stream",
        json={"message": "help me with my calculus homework", "chat_id": chat_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    errors = _error_lines(resp.text)
    assert errors, "stream must surface an error event when no LLM config exists"
    assert "No LLM config set" in json.loads(errors[0].removeprefix("data: "))["content"]


async def test_chat_stream_empty_config_streams_error(client, auth_and_chat_no_config):
    """A created-but-empty config (no chat order) also fails over to an error event."""
    from app.llmconfig.model import LLMConfig

    chat_id = await auth_and_chat_no_config()
    token = _make_token()
    await _save_config_for_alice(LLMConfig(triplets=[]))

    resp = await client.post(
        "/api/chat/stream",
        json={"message": "help me with my calculus homework", "chat_id": chat_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    errors = _error_lines(resp.text)
    assert errors
    assert "No models configured" in json.loads(errors[0].removeprefix("data: "))["content"]


async def test_chat_stream_resolves_configured_models(client, auth_and_chat):
    """Happy path: the chat loop routes to the configured chat & memory models."""
    from app.llmconfig import security
    from app.llmconfig.model import LLMConfig, OperationConfig, Triplet

    chat_id = await auth_and_chat()
    token = _make_token()
    await _save_config_for_alice(LLMConfig(
        triplets=[
            Triplet(alias="primary", provider="openai", model="gpt-4", api_key=security.encrypt("k")),
            Triplet(alias="mem", provider="openai", model="gpt-4o-mini", api_key=security.encrypt("k")),
        ],
        chat=OperationConfig(order=["primary"], rules=[]),
        memory=OperationConfig(order=["mem"], rules=[]),
    ))

    seen = {"chat": [], "memory": []}

    async def _handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        req = json.loads(body) if body else {}
        is_stream = req.get("stream", False)
        key = "chat" if is_stream else "memory"
        seen[key].append(req.get("model"))
        if key == "memory":
            return httpx.Response(200, json={
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "model": req.get("model"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "title"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            })
        return httpx.Response(200, content=_sse_stream(["Hello ", "world"]), headers={"Content-Type": "text/event-stream"})

    transport = httpx.MockTransport(_handler)
    mock_client = httpx.AsyncClient(transport=transport)

    with patch("langchain_openai.chat_models.base._get_default_async_httpx_client", return_value=mock_client):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "help me with my calculus homework", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert seen["chat"] == ["gpt-4"], "chat op must resolve to its configured model"
    assert seen["memory"] == ["gpt-4o-mini"], "memory op (title) must resolve to its configured model"
    token_lines = [l for l in resp.text.split("\n") if l.strip() and '"type": "token"' in l]
    full = "".join(json.loads(l.removeprefix("data: "))["content"] for l in token_lines)
    assert full == "Hello world"


async def test_chat_stream_fails_over_on_rate_limit(client, auth_and_chat):
    """Primary model 429s; the fallback model must stream the reply."""
    from app.llmconfig import security
    from app.llmconfig.model import LLMConfig, OperationConfig, Triplet

    chat_id = await auth_and_chat()
    token = _make_token()
    await _save_config_for_alice(LLMConfig(
        triplets=[
            Triplet(alias="primary", provider="openai", model="gpt-4", api_key=security.encrypt("k")),
            Triplet(alias="backup", provider="openai", model="gpt-4o-mini", api_key=security.encrypt("k")),
        ],
        chat=OperationConfig(order=["primary", "backup"], rules=[]),
        memory=OperationConfig(order=["primary", "backup"], rules=[]),
    ))

    seen_models = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        req = json.loads(body) if body else {}
        if not req.get("stream", False):
            return httpx.Response(200, json={
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "model": "gpt-4",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "title"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            })
        seen_models.append(req.get("model"))
        if seen_models[-1] == "gpt-4":
            return httpx.Response(429, json={"error": {"message": "quota"}})
        return httpx.Response(200, content=_sse_stream(["Hello ", "world"]), headers={"Content-Type": "text/event-stream"})

    transport = httpx.MockTransport(_handler)
    mock_client = httpx.AsyncClient(transport=transport)

    with patch("langchain_openai.chat_models.base._get_default_async_httpx_client", return_value=mock_client):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "help me with my calculus homework", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert seen_models == ["gpt-4", "gpt-4o-mini"], "expected primary then fallback model calls"
    token_lines = [l for l in resp.text.split("\n") if l.strip() and '"type": "token"' in l]
    full = "".join(json.loads(l.removeprefix("data: "))["content"] for l in token_lines)
    assert full == "Hello world"


async def test_chat_stream_all_models_fail_streams_error(client, auth_and_chat):
    """If every alias errors, the chat loop must stream an error instead of 500ing."""
    from app.llmconfig import security
    from app.llmconfig.model import LLMConfig, OperationConfig, Triplet

    chat_id = await auth_and_chat()
    token = _make_token()
    await _save_config_for_alice(LLMConfig(
        triplets=[
            Triplet(alias="primary", provider="openai", model="gpt-4", api_key=security.encrypt("k")),
            Triplet(alias="backup", provider="openai", model="gpt-4o-mini", api_key=security.encrypt("k")),
        ],
        chat=OperationConfig(order=["primary", "backup"], rules=[]),
        memory=OperationConfig(order=["primary", "backup"], rules=[]),
    ))

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}})

    transport = httpx.MockTransport(_handler)
    mock_client = httpx.AsyncClient(transport=transport)

    with patch("langchain_openai.chat_models.base._get_default_async_httpx_client", return_value=mock_client):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "help me with my calculus homework", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    errors = _error_lines(resp.text)
    assert errors, "stream must surface an error when every model fails"
