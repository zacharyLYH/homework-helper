"""Scriptable OpenAI-compatible mock LLM server for the e2e harness.

The backend is pointed at this process via ``PROVIDER_BASE_URL_OVERRIDE``, so
its real provider clients (chat streaming, title generation, memory-worker
evaluation) make genuine HTTP calls here instead of to a commercial provider.

Two ways to script it, both matching on request content:

    POST /__control/route   register one-shot memory-eval specs; a spec whose
                            ``match`` substring appears in the eval prompt is
                            served once (used to script the *worker's* LLM)
    POST /__control/reset   clear routes and the call log
    GET  /__control/log     list every /chat/completions call we received
    GET  /__control/health  readiness probe

Anything unscripted gets a benign default (skip eval for the worker / title
calls, a short text reply for streaming chat), so a call never hard-fails a
test. The call log keeps the full request ``messages`` so tests can assert
what the backend actually sent (e.g. injected memory context).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import FastAPI, Request, Response

app = FastAPI()

ROUTES: list[dict[str, Any]] = []
CALLS: list[dict[str, Any]] = []

_DEFAULT_REPLY = "The answer is 4."

# Marker unique to the memory worker's eval prompt (memory/prompts.py). Gates
# route matching so title-generation calls that happen to embed the user's
# turn text can never consume a route meant for an eval.
_EVAL_MARKER = "CURRENT MEMORY STATE"


def _pick_memory_spec(body: dict[str, Any]) -> tuple[str, float] | None:
    """Return (JSON payload, delay in seconds) for a non-streaming call, or None.

    A spec serves ``times`` eval attempts (default one-shot), counted at pick
    time so a killed worker's attempt still consumes one slot. ``delay_ms``
    applies to attempt 1, ``retry_delay_ms`` to later attempts — a reclaimed
    retry re-matches the same spec, and its delay must fit the worker's LLM
    timeout (tests model 'provider was slow once, then recovered').
    """
    text = _messages_text(body.get("messages"))
    if _EVAL_MARKER not in text:
        return None  # title generation etc. — organic skip
    for route in list(ROUTES):
        if route["match"] in text:
            attempt = int(route.get("_picked", 0)) + 1
            route["_picked"] = attempt
            if attempt >= int(route.get("times", 1)):
                ROUTES.remove(route)  # consumed
            first = float(route.get("delay_ms", 0))
            retry = float(route.get("retry_delay_ms", first))
            delay = first if attempt == 1 else retry
            return json.dumps(route["memory"]), delay / 1000.0
    return None  # unscripted eval — organic skip


def _sse_chunk(delta: dict[str, Any], finish: str | None = None) -> str:
    choice: dict[str, Any] = {"index": 0, "delta": delta}
    if finish is not None:
        choice["finish_reason"] = finish
    return f"data: {json.dumps({'id': 'chatcmpl-mock', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'mock', 'choices': [choice]})}\n\n"


def _render_sse(text: str) -> str:
    parts = text.split(" ")
    out: list[str] = []
    for i, word in enumerate(parts):
        suffix = " " if i < len(parts) - 1 else ""
        out.append(_sse_chunk({"content": word + suffix}))
    out.append(
        f"data: {json.dumps({'id': 'chatcmpl-mock', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'mock', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 30, 'completion_tokens': 5, 'total_tokens': 35}})}\n\n"
    )
    out.append("data: [DONE]\n\n")
    return "".join(out)


def _render_json(content: str) -> str:
    return json.dumps(
        {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": 0,
            "model": "mock",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35},
        }
    )


def _messages_text(messages: Any) -> str:
    if not isinstance(messages, list):
        return str(messages or "")
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "") if isinstance(m, dict) else ""
        content = m.get("content", "") if isinstance(m, dict) else str(m or "")
        if isinstance(content, list):  # multimodal message parts
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict) and p.get("text")
            )
        # Truncate per-message so the log stays small, but keep it large enough
        # that the agent system prompt (~2.6k chars) plus an appended memory
        # context block survive intact — tests assert against that block.
        lines.append(f"{role}: {str(content)[:8000]}")
    return "\n".join(lines)


async def _chat_completions(request: Request) -> Response:
    body = await request.json()
    is_stream = bool(body.get("stream", False))
    text = _messages_text(body.get("messages"))

    if is_stream:
        content = _DEFAULT_REPLY
        delay_s = 0.0
    else:
        picked = _pick_memory_spec(body)
        if picked is None:
            content = json.dumps({"skip": True})
            delay_s = 0.0
        else:
            content, delay_s = picked

    # Logged on ARRIVAL, before honoring any delay — the log is the test's
    # signal that a request is in flight (e.g. the safe moment to kill a
    # worker mid-eval in crash tests).
    CALLS.append(
        {
            "index": len(CALLS) + 1,
            "stream": is_stream,
            "reply": content[:300],
            "text": text,
            "ts": time.time(),
        }
    )

    if delay_s > 0:  # e.g. tests holding a job in 'running' for dedup
        await asyncio.sleep(delay_s)

    if is_stream:
        return Response(content=_render_sse(content), media_type="text/event-stream")
    return Response(content=_render_json(content), media_type="application/json")


# The backend appends "/chat/completions" to the provider base URL, so our
# override ("/v1") may produce either path depending on how a client is built.
app.add_api_route("/chat/completions", _chat_completions, methods=["POST"])
app.add_api_route("/v1/chat/completions", _chat_completions, methods=["POST"])


@app.post("/__control/reset")
def control_reset() -> dict[str, int]:
    ROUTES.clear()
    CALLS.clear()
    return {"routes": 0, "calls": 0}


@app.post("/__control/route")
async def control_route(request: Request) -> dict[str, int]:
    """Register content-routed memory-eval specs (one-shot unless ``times``)."""
    body = await request.json()
    specs = body if isinstance(body, list) else [body]
    for s in specs:
        assert "match" in s, "routed spec needs a 'match' substring"
        assert "memory" in s, "routed spec needs a 'memory' payload"
        assert int(s.get("times", 1)) >= 1, "times must be >= 1"
        ROUTES.append(s)
    return {"routes": len(ROUTES)}


@app.get("/__control/log")
def control_log() -> list[dict[str, Any]]:
    return list(CALLS)


@app.get("/__control/health")
def control_health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import sys

    import uvicorn

    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 9797
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
