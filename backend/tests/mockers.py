import json
from unittest.mock import patch

import httpx
from langchain_openai import ChatOpenAI
from pydantic import SecretStr


def mock_llm(content: str = "Hello!", model: str = "gpt-4"):
    """Patch _make_llm to return a real ChatOpenAI with a mocked HTTP transport.

    Only the HTTP call to the LLM provider is intercepted — all LangChain
    and LangGraph plumbing runs for real.
    """

    async def _handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        req = json.loads(body) if body else {}
        is_stream = req.get("stream", False)

        if is_stream:
            async def _sse_body():
                words = content.split(" ")
                for i, word in enumerate(words):
                    suffix = " " if i < len(words) - 1 else ""
                    yield _sse(json.dumps({
                        "id": "chatcmpl-mock",
                        "object": "chat.completion.chunk",
                        "created": 1677652288,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": word + suffix}, "finish_reason": None}],
                    }))
                yield _sse(json.dumps({
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "created": 1677652288,
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20},
                }))
                yield b"data: [DONE]\n\n"

            return httpx.Response(
                200,
                content=_sse_body(),
                headers={"Content-Type": "text/event-stream"},
            )

        return httpx.Response(200, json={
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": 1677652288,
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20},
        })

    def _sse(data: str) -> bytes:
        return f"data: {data}\n\n".encode()

    transport = httpx.MockTransport(_handler)
    http_async_client = httpx.AsyncClient(transport=transport)

    def _make_mock_llm(model_name: str) -> ChatOpenAI:
        return ChatOpenAI(
            http_async_client=http_async_client,
            api_key=SecretStr("sk-fake"),
            model=model_name,
            temperature=0.7,
            max_completion_tokens=1024,
        )

    return patch("app.llm._make_llm", side_effect=_make_mock_llm)


def mock_title_llm(title: str = "Test Chat Title"):
    from unittest.mock import MagicMock

    mock = MagicMock()

    async def _mock_astream(prompt):
        chunk = MagicMock()
        chunk.content = title
        yield chunk

    mock.astream = _mock_astream
    return patch("app.routes.chat.title_llm", mock)


def mock_email_send():
    return patch("app.routes.auth.send_verification_email", return_value=True)


def mock_email_send_failure():
    return patch("app.routes.auth.send_verification_email", return_value=False)
