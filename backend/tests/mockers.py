import json
from unittest.mock import patch

import httpx


def mock_llm(content: str = "Hello!", model: str = "gpt-4"):
    """Intercept HTTP calls so the real _make_llm & ChatOpenAI work.

    Patches _get_default_async_httpx_client so every ChatOpenAI created
    during the patch uses a mock transport instead of real HTTP.
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
    mock_client = httpx.AsyncClient(transport=transport)

    return patch(
        "langchain_openai.chat_models.base._get_default_async_httpx_client",
        return_value=mock_client,
    )


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
