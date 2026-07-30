import json

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


@pytest.fixture
def auth_and_chat(client, seed):
    seed(users=["alice@school.edu"])

    async def _setup():
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
        chat_id = chat_resp.json()["id"]
        return chat_id

    return _setup


# ── happy path (existing) ────────────────────────────────────────────


async def test_chat_stream_events(client, auth_and_chat):
    chat_id = await auth_and_chat()
    token = _make_token()

    with mock_llm(content="Hello world"), mock_title_llm("Test Title"):
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "What is 2+2?", "chat_id": chat_id},
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


async def test_chat_stream_unicode_message(client, auth_and_chat):
    chat_id = await auth_and_chat()
    token = _make_token()

    with mock_llm(content="¡Hola! 你好 こんにちは"), mock_title_llm():
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "π ≈ 3.14159 🎉", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    lines = [l for l in resp.text.split("\n") if l.strip()]
    token_lines = [l for l in lines if '"type": "token"' in l]

    full = "".join(json.loads(l.removeprefix("data: "))["content"] for l in token_lines)
    assert full == "¡Hola! 你好 こんにちは"

    with get_conn() as conn:
        msgs = conn.execute(
            "SELECT content FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()
        assert msgs[0]["content"] == "π ≈ 3.14159 🎉"
        assert msgs[1]["content"] == "¡Hola! 你好 こんにちは"


async def test_chat_stream_with_image(client, auth_and_chat):
    chat_id = await auth_and_chat()
    token = _make_token()
    image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    with mock_llm(content="Image received"), mock_title_llm("Test Title"):
        resp = await client.post(
            "/api/chat/stream",
            json={
                "message": "What is in this image?",
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
    assert msgs[0]["content"] == "What is in this image?"
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
            json={"message": "First message", "chat_id": chat_id},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp1.status_code == 200

    with mock_llm(content="Second reply"), mock_title_llm():
        resp2 = await client.post(
            "/api/chat/stream",
            json={"message": "Second message", "chat_id": chat_id},
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
        {"role": "user", "content": "First message"},
        {"role": "assistant", "content": "First reply"},
        {"role": "user", "content": "Second message"},
        {"role": "assistant", "content": "Second reply"},
    ]

    lines = [l for l in resp2.text.split("\n") if l.strip()]
    token_lines = [l for l in lines if '"type": "token"' in l]
    full = "".join(json.loads(l.removeprefix("data: "))["content"] for l in token_lines)
    assert full == "Second reply"


# ── quote field ──────────────────────────────────────────────────────


async def test_chat_stream_with_quote(client, auth_and_chat):
    """Quote field is accepted, not stored in DB, and doesn't break streaming."""
    chat_id = await auth_and_chat()
    token = _make_token()

    with mock_llm(content="Here is the refined explanation."), mock_title_llm("Test Title"):
        resp = await client.post(
            "/api/chat/stream",
            json={
                "message": "Can you explain this more clearly?",
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
    assert msgs[0]["content"] == "Can you explain this more clearly?"
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
            json={"message": "Hello", "chat_id": chat_id, "quote": ""},
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
