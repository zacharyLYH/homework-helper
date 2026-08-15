import json
from unittest.mock import patch

import httpx
import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage
from openai import RateLimitError

from app.db import get_conn
from app.llmconfig import router
from app.llmconfig.router import LLMRoutingError
from tests.mockers import seed_llm_config


def _insert_user(email: str = "bob@school.edu") -> int:
    with get_conn() as conn:
        conn.execute("INSERT INTO users (email) VALUES (?)", (email,))
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    return row["id"]


def _patch_transport(handler):
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return patch(
        "langchain_openai.chat_models.base._get_default_async_httpx_client",
        return_value=client,
    )


def _sse(body: bytes) -> httpx.Response:
    return httpx.Response(200, content=body, headers={"Content-Type": "text/event-stream"})


def _success_stream_body(content: str = "hello") -> bytes:
    chunk1 = (
        f'data: {{"id":"cmpl","object":"chat.completion.chunk","model":"gpt-4",'
        f'"choices":[{{"index":0,"delta":{{"content":"{content}"}},"finish_reason":null}}]}}\n\n'
    )
    chunk2 = (
        'data: {"id":"cmpl","object":"chat.completion.chunk","model":"gpt-4",'
        '"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    return (chunk1 + chunk2).encode()


def _non_stream_body(content: str = "title") -> bytes:
    return json.dumps(
        {
            "id": "cmpl",
            "object": "chat.completion",
            "model": "gpt-4",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }
    ).encode()


# ── classify_error ───────────────────────────────────────────────────


def test_classify_error_maps_429_to_rate_limit():
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request)
    exc = RateLimitError(
        "rate limit", response=response, body={"error": {"message": "quota"}}
    )
    assert router.classify_error(exc) == "rate_limit"


def test_classify_error_maps_5xx_to_server_error():
    exc = httpx.HTTPStatusError("boom", request=httpx.Request("POST", "http://x"), response=httpx.Response(503))
    assert router.classify_error(exc) == "server_error"


def test_classify_error_does_not_retry_client_errors():
    exc = httpx.HTTPStatusError("bad request", request=httpx.Request("POST", "http://x"), response=httpx.Response(400))
    assert router.classify_error(exc) is None


def test_classify_error_maps_timeout_to_server_error():
    assert router.classify_error(httpx.TimeoutException("slow")) == "server_error"


def test_classify_error_returns_none_for_other_errors():
    assert router.classify_error(ValueError("nope")) is None


def test_classify_error_maps_generic_status_code():
    class _Exc(Exception):
        status_code = 429

    assert router.classify_error(_Exc()) == "rate_limit"


# ── stream ───────────────────────────────────────────────────────────


async def test_stream_no_config_raises(setup_test_db):
    user_id = _insert_user()
    with pytest.raises(LLMRoutingError):
        async for _ in router.stream([HumanMessage(content="hi")], user_id=user_id):
            pass


async def test_stream_uses_chat_order(setup_test_db):
    user_id = _insert_user()
    seed_llm_config(user_id, aliases=("primary",))

    seen_models = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        req = json.loads(body) if body else {}
        seen_models.append(req.get("model"))
        assert req.get("stream") is True
        return _sse(_success_stream_body())

    with _patch_transport(_handler):
        chunks = []
        async for chunk in router.stream(
            [HumanMessage(content="hello")], user_id=user_id, operation="chat"
        ):
            chunks.append(chunk)

    assert chunks, "expected at least one streamed chunk"
    assert all(isinstance(c, AIMessageChunk) for c in chunks)
    assert seen_models == ["gpt-4"]


async def test_stream_fails_over_to_next_alias_on_rate_limit(setup_test_db):
    user_id = _insert_user()
    seed_llm_config(user_id, aliases=("primary", "fallback"), models=("gpt-4", "gpt-4o-mini"))
    calls = {"n": 0, "models": []}

    async def _handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        req = json.loads(body) if body else {}
        calls["models"].append(req.get("model"))
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "quota"}})
        return _sse(_success_stream_body())

    with _patch_transport(_handler):
        chunks = []
        async for chunk in router.stream(
            [HumanMessage(content="hello")], user_id=user_id, operation="chat"
        ):
            chunks.append(chunk)

    assert calls["n"] == 2
    assert calls["models"] == ["gpt-4", "gpt-4o-mini"]
    assert chunks, "fallback model must stream output"


async def test_stream_fails_over_on_server_error(setup_test_db):
    user_id = _insert_user()
    seed_llm_config(user_id, aliases=("primary", "fallback"), models=("gpt-4", "gpt-4o-mini"))
    calls = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(await request.aread()).get("model"))
        if len(calls) == 1:
            return httpx.Response(503, json={"error": {"message": "down"}})
        return _sse(_success_stream_body())

    with _patch_transport(_handler):
        async for _ in router.stream(
            [HumanMessage(content="hello")], user_id=user_id, operation="chat"
        ):
            pass

    assert calls == ["gpt-4", "gpt-4o-mini"]


async def test_stream_stops_on_non_retryable_error(setup_test_db):
    user_id = _insert_user()
    seed_llm_config(user_id, aliases=("primary", "fallback"))
    calls = []

    async def _fake_stream_model(messages, *, base_url, api_key, model, bind_tools=None, config=None):
        calls.append(model)
        raise ValueError("invalid request")
        yield  # make this an async generator

    with pytest.raises(ValueError), pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(router, "stream_model", _fake_stream_model)
        async for _ in router.stream(
            [HumanMessage(content="hello")], user_id=user_id, operation="chat"
        ):
            pass

    assert calls == ["gpt-4"]


async def test_stream_skips_unusable_key(setup_test_db):
    from app.llmconfig import security, store
    from app.llmconfig.model import LLMConfig, OperationConfig, Triplet

    user_id = _insert_user()
    cfg = LLMConfig(
        triplets=[
            Triplet(alias="bad", provider="openai", model="bad-model", api_key="not-a-token"),
            Triplet(alias="good", provider="openai", model="good-model", api_key=security.encrypt("k")),
        ],
        chat=OperationConfig(order=["bad", "good"]),
        memory=OperationConfig(order=["good"]),
    )
    store.save_config(user_id, cfg)
    calls = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(await request.aread()).get("model"))
        return _sse(_success_stream_body())

    with _patch_transport(_handler):
        async for _ in router.stream(
            [HumanMessage(content="hello")], user_id=user_id, operation="chat"
        ):
            pass

    assert calls == ["good-model"]


async def test_stream_does_not_fail_over_after_output(setup_test_db, monkeypatch):
    user_id = _insert_user()
    seed_llm_config(user_id, aliases=("primary", "fallback"))
    calls = []

    async def _fake_stream_model(messages, *, base_url, api_key, model, bind_tools=None, config=None):
        calls.append(model)
        if model == "gpt-4":
            yield AIMessageChunk(content="partial")
            raise httpx.ReadError("connection lost")
        yield AIMessageChunk(content="fallback")

    monkeypatch.setattr(router, "stream_model", _fake_stream_model)
    with pytest.raises(httpx.ReadError):
        async for _ in router.stream(
            [HumanMessage(content="hello")], user_id=user_id, operation="chat"
        ):
            pass

    assert calls == ["gpt-4"]


async def test_stream_uses_rule_use_list_over_order(setup_test_db):
    from app.llmconfig import security, store
    from app.llmconfig.model import LLMConfig, OperationConfig, RoutingRule, Triplet

    user_id = _insert_user()
    cfg = LLMConfig(
        triplets=[
            Triplet(alias="primary", provider="openai", model="gpt-4", api_key=security.encrypt("k")),
            Triplet(alias="backup", provider="openai", model="gpt-4o-mini", api_key=security.encrypt("k")),
            Triplet(alias="last", provider="openai", model="gpt-4o", api_key=security.encrypt("k")),
        ],
        chat=OperationConfig(
            order=["primary", "last"],
            rules=[RoutingRule(when="rate_limit", use=["backup"])],
        ),
        memory=OperationConfig(order=["primary"]),
    )
    store.save_config(user_id, cfg)

    calls = {"n": 0, "models": []}

    async def _handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        req = json.loads(body) if body else {}
        calls["models"].append(req.get("model"))
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "quota"}})
        return _sse(_success_stream_body())

    with _patch_transport(_handler):
        async for _ in router.stream(
            [HumanMessage(content="hello")], user_id=user_id, operation="chat"
        ):
            pass

    assert calls["models"] == ["gpt-4", "gpt-4o-mini"], "rule.use must win over order"


async def test_stream_raises_last_error_when_all_models_fail(setup_test_db):
    user_id = _insert_user()
    seed_llm_config(user_id, aliases=("primary", "fallback"))
    calls = {"n": 0}

    async def _handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": {"message": "quota"}})

    with _patch_transport(_handler), pytest.raises(RateLimitError):
        async for _ in router.stream(
            [HumanMessage(content="hello")], user_id=user_id, operation="chat"
        ):
            pass

    assert calls["n"] == 2, "both aliases must be tried before giving up"


# ── generate ─────────────────────────────────────────────────────────


async def test_generate_returns_text(setup_test_db):
    user_id = _insert_user()
    seed_llm_config(user_id, aliases=("primary",))

    async def _handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        req = json.loads(body) if body else {}
        assert req.get("stream", False) is False
        return httpx.Response(200, content=_non_stream_body("My Title"))

    with _patch_transport(_handler):
        title = await router.generate("Make a title", user_id=user_id, operation="memory")

    assert title == "My Title"


async def test_generate_fails_over_to_next_alias(setup_test_db):
    user_id = _insert_user()
    seed_llm_config(user_id, aliases=("primary", "fallback"))
    calls = 0

    async def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": {"message": "down"}})
        return httpx.Response(200, content=_non_stream_body("fallback title"))

    with _patch_transport(_handler):
        title = await router.generate("Make a title", user_id=user_id, operation="memory")

    assert title == "fallback title"
    assert calls == 2


async def test_generate_no_config_raises(setup_test_db):
    user_id = _insert_user()
    with pytest.raises(LLMRoutingError):
        await router.generate("Make a title", user_id=user_id, operation="memory")
