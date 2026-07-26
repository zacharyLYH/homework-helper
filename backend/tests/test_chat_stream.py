import json

import pytest

from app.db import get_conn
from tests.mockers import mock_llm, mock_title_llm


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
        chat_resp = await client.post("/api/chats", params={"subject_id": subject_id, "mode": "guide"})
        chat_id = chat_resp.json()["id"]
        return chat_id
    return _setup


async def test_chat_stream_events(client, auth_and_chat):
    chat_id = await auth_and_chat()

    from app.auth import create_access_token
    from app.db import get_conn as _get_conn
    from app.schemas import User as _User
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = 'alice@school.edu'").fetchone()
    user = _User(id=row["id"], email=row["email"], created_at=row["created_at"])
    token = create_access_token(user)

    with (
        mock_llm(content="Hello world"),
        mock_title_llm("Test Title"),
    ):
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
    assert done_data["type"] == "done"
    assert done_data["model"] == "gpt-4"
    assert done_data["usage"]["input_tokens"] == 15
    assert done_data["usage"]["output_tokens"] == 5
    assert done_data["usage"]["total_tokens"] == 20

    with get_conn() as conn:
        messages = conn.execute(
            "SELECT role, content, token_count FROM messages WHERE chat_id = ? ORDER BY created_at",
            (chat_id,),
        ).fetchall()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "What is 2+2?"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hello world"
        assert messages[1]["token_count"] == 20

        chat = conn.execute("SELECT total_tokens, input_tokens, output_tokens, title FROM chats WHERE id = ?", (chat_id,)).fetchone()
        assert chat["total_tokens"] == 20
        assert chat["input_tokens"] == 15
        assert chat["output_tokens"] == 5
