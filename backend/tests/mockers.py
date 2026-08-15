import json
from unittest.mock import patch

import httpx


def seed_llm_config(
    user_id: int,
    *,
    api_key: str = "sk-test-key",
    aliases=("primary",),
    models=None,
    chat_aliases=None,
    memory_aliases=None,
):
    """Write a minimal valid LLM config for a user into the main DB.

    Without a config the router refuses to call any model, so chat/title tests
    must seed one before hitting /api/chat/stream.
    """
    from app.llmconfig import security, store
    from app.llmconfig.model import LLMConfig, OperationConfig, Triplet

    triplet_list = [
        Triplet(
            alias=alias,
            provider="openai",
            model=(models[i] if models else "gpt-4"),
            api_key=security.encrypt(api_key),
        )
        for i, alias in enumerate(aliases)
    ]
    cfg = LLMConfig(
        triplets=triplet_list,
        chat=OperationConfig(order=list(chat_aliases or aliases), rules=[]),
        memory=OperationConfig(order=list(memory_aliases or aliases), rules=[]),
    )
    store.save_config(user_id, cfg)
    return cfg


def mock_tool_llm(
    tool_name: str | None,
    tool_args: str,
    text_after_tool: str = "The answer is 4.",
    model: str = "gpt-4",
):
    """Mock LLM that simulates a tool-calling ReAct loop.

    1st LLM call → responds with tool call chunks (name + args)
    2nd+ LLM calls → respond with text_after_tool word-by-word

    Only mocks the async httpx client — everything else (graph, tools, DB)
    executes real code.
    """
    call_count = [0]

    async def _handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        body = await request.aread()
        req = json.loads(body) if body else {}
        is_stream = req.get("stream", False)

        if not is_stream:
            return httpx.Response(200, json={
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": 1677652288,
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": text_after_tool},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35},
            })

        is_first_call = call_count[0] == 1

        if is_first_call and tool_name:
            # First call: return tool call chunks
            tc_id = "call_mock_tc_001"
            async def _sse_body():
                yield _sse(json.dumps({
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "created": 1677652288,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "tool_calls": [{
                                "index": 0,
                                "id": tc_id,
                                "type": "function",
                                "function": {"name": tool_name, "arguments": ""},
                            }]
                        },
                        "finish_reason": None,
                    }],
                }))
                yield _sse(json.dumps({
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "created": 1677652288,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "tool_calls": [{
                                "index": 0,
                                "function": {"arguments": tool_args},
                            }]
                        },
                        "finish_reason": None,
                    }],
                }))
                yield _sse(json.dumps({
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "created": 1677652288,
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
                }))
                yield b"data: [DONE]\n\n"

            return httpx.Response(
                200,
                content=_sse_body(),
                headers={"Content-Type": "text/event-stream"},
            )
        else:
            # Subsequent calls: return text token-by-token
            async def _sse_body():
                words = text_after_tool.split(" ")
                for i, word in enumerate(words):
                    suffix = " " if i < len(words) - 1 else ""
                    yield _sse(json.dumps({
                        "id": "chatcmpl-mock",
                        "object": "chat.completion.chunk",
                        "created": 1677652288,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": word + suffix},
                            "finish_reason": None,
                        }],
                    }))
                yield _sse(json.dumps({
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "created": 1677652288,
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35},
                }))
                yield b"data: [DONE]\n\n"

            return httpx.Response(
                200,
                content=_sse_body(),
                headers={"Content-Type": "text/event-stream"},
            )

    def _sse(data: str) -> bytes:
        return f"data: {data}\n\n".encode()

    transport = httpx.MockTransport(_handler)
    mock_client = httpx.AsyncClient(transport=transport)
    return patch(
        "langchain_openai.chat_models.base._get_default_async_httpx_client",
        return_value=mock_client,
    )


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
    """Patch the title generator so a fixed title streams out."""
    async def _fake_title_stream(chat_id: int, user_id: int):
        yield title

    return patch("app.routes.chat.generate_title_stream", _fake_title_stream)


def mock_email_send():
    return patch("app.routes.auth.send_verification_email", return_value=True)


def mock_email_send_failure():
    return patch("app.routes.auth.send_verification_email", return_value=False)
