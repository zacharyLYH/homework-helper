"""Resolve a user's LLM config into live model calls with failover.

This is the single place chat/title/memory operations turn a stored
:class:`LLMConfig` into real HTTP calls. Every request:

1. loads the user's config from ``users.llm_config_yaml``
2. walks the operation's ``order`` list (primary first, fallbacks after)
3. decrypts each triplet's API key only at call time
4. on ``rate_limit``/``server_error`` failover to the next alias, preferring a
   routing rule's ``use`` list when one matches the reason
5. raises :class:`LLMRoutingError` when nothing usable is left
"""

from collections import deque
from collections.abc import AsyncGenerator, Callable
from typing import Any

import httpx
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from openai import APITimeoutError, RateLimitError

from app.llm import invoke_model, stream_model
from app.llmconfig import security, store
from app.llmconfig.catalog import get_provider
from app.llmconfig.model import LLMConfig, OperationConfig, ROUTING_REASONS, Triplet
from app.logging import structured_log


class LLMRoutingError(RuntimeError):
    """Raised when no usable model could be found for a request."""


def classify_error(exc: Exception) -> str | None:
    """Map an exception to a routing reason, or ``None`` when not retryable.

    ``429`` → ``rate_limit``; HTTP ``5xx`` and transport/timeout failures →
    ``server_error``. Anything else (e.g. ``400``, auth errors) is returned as
    ``None`` so the router stops rather than retrying a doomed call.
    """
    if isinstance(exc, RateLimitError):
        return "rate_limit"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return "rate_limit"
        if status >= 500:
            return "server_error"
        return None
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status == 429:
            return "rate_limit"
        if status >= 500:
            return "server_error"
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return "server_error"
    if isinstance(exc, APITimeoutError):
        return "server_error"
    return None


def _resolve_operation(cfg: LLMConfig, operation: str) -> OperationConfig:
    if operation == "chat":
        return cfg.chat
    if operation == "memory":
        return cfg.memory
    raise LLMRoutingError(f"Unknown operation: {operation}")


async def _execute(
    user_id: int | None,
    operation: str,
    call: Callable[[Triplet, str, str], AsyncGenerator[Any, None]],
) -> AsyncGenerator[Any, None]:
    """Walk the operation's alias chain, calling ``call`` per usable triplet.

    ``call`` is an async generator invoked with ``(triplet, base_url, api_key)``;
    it must ``yield`` streaming values and let exceptions propagate so the
    router can classify and fail over.
    """
    cfg = store.get_config(user_id)
    if cfg is None:
        raise LLMRoutingError("No LLM config set. Configure one in Settings first.")
    op = _resolve_operation(cfg, operation)
    if not op.order:
        raise LLMRoutingError(f"No models configured for '{operation}'.")

    by_alias = {t.alias: t for t in cfg.triplets}
    queue: deque[str] = deque(op.order)
    used_rules: set[str] = set()
    last_err: Exception | None = None

    while queue:
        alias = queue.popleft()
        triplet = by_alias.get(alias)
        if triplet is None:
            continue
        provider = get_provider(triplet.provider)
        key = security.decrypt_safe(triplet.api_key)
        structured_log(
            "llm_key_resolved",
            operation=operation,
            alias=alias,
            provider=triplet.provider,
            model=triplet.model,
            key_present=key is not None,
        )
        if provider is None or key is None:
            structured_log(
                "llm_skip",
                operation=operation,
                alias=alias,
                reason="unusable_triplet",
                provider=triplet.provider,
            )
            continue

        emitted = False
        try:
            async for item in call(triplet, provider.base_url, key):
                emitted = True
                yield item
            return
        except Exception as exc:
            last_err = exc
            if emitted:
                raise
            reason = classify_error(exc)
            if reason not in ROUTING_REASONS:
                raise
            structured_log(
                "llm_failover",
                operation=operation,
                alias=alias,
                reason=reason,
                error=str(exc)[:300],
            )
            if reason in ROUTING_REASONS and reason not in used_rules:
                rule = next((r for r in op.rules if r.when == reason), None)
                if rule and rule.use:
                    used_rules.add(reason)
                    queue = deque(rule.use) + queue

    if last_err is not None:
        raise last_err
    raise LLMRoutingError("No usable LLM configured.")


async def stream(
    messages: list,
    *,
    user_id: int | None,
    operation: str = "chat",
    bind_tools: list | None = None,
    config: RunnableConfig | None = None,
) -> AsyncGenerator[BaseMessage, None]:
    """Stream a response for the user's ``chat``/``memory`` operation chain."""

    async def _call(
        triplet: Triplet, base_url: str, api_key: str
    ) -> AsyncGenerator[BaseMessage, None]:
        async for chunk in stream_model(
            messages,
            base_url=base_url,
            api_key=api_key,
            model=triplet.model,
            bind_tools=bind_tools,
            config=config,
        ):
            yield chunk

    async for chunk in _execute(user_id, operation, _call):
        yield chunk


async def generate(
    prompt: str,
    *,
    user_id: int | None,
    operation: str = "memory",
) -> str:
    """Invoke the user's chain once (non-streaming) and return the text."""

    async def _call(
        triplet: Triplet, base_url: str, api_key: str
    ) -> AsyncGenerator[str, None]:
        yield await invoke_model(prompt, base_url=base_url, api_key=api_key, model=triplet.model)

    async for item in _execute(user_id, operation, _call):
        return item
    raise LLMRoutingError("No usable LLM configured.")
