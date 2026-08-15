"""Test-ping helper: fire every unique (provider, model, api key) combination.

Used by the "Test config" button. Each triplet gets one minimal, cheap request
and we report status + latency so users can verify keys and models work.
"""

import time

import httpx

from app.llmconfig import security
from app.llmconfig.catalog import get_provider
from app.llmconfig.model import LLMConfig

PING_PROMPT = "Reply with exactly one word: pong"
PING_TIMEOUT_S = 30.0


def _classify(status_code: int) -> str:
    if status_code == 429:
        return "rate_limit"
    if status_code >= 500:
        return "server_error"
    return "http_error"


async def ping_triplet(
    *,
    alias: str,
    provider: str,
    model: str,
    encrypted_key: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    prov = get_provider(provider)
    if prov is None:
        return {"alias": alias, "provider": provider, "model": model, "ok": False, "error": f"Unknown provider '{provider}'", "latency_ms": None}

    key = security.decrypt_safe(encrypted_key)
    if not key:
        return {"alias": alias, "provider": provider, "model": model, "ok": False, "error": "Missing API key", "latency_ms": None}

    url = prov.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PING_PROMPT}],
        "max_tokens": 5,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=PING_TIMEOUT_S, transport=transport) as client:
            resp = await client.post(url, json=payload, headers=headers)
        latency_ms = int((time.monotonic() - start) * 1000)
        if resp.status_code == 200:
            return {
                "alias": alias,
                "provider": provider,
                "model": model,
                "ok": True,
                "error": None,
                "latency_ms": latency_ms,
                "kind": "ok",
            }
        return {
            "alias": alias,
            "provider": provider,
            "model": model,
            "ok": False,
            "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            "latency_ms": latency_ms,
            "kind": _classify(resp.status_code),
        }
    except httpx.TimeoutException:
        return {"alias": alias, "provider": provider, "model": model, "ok": False, "error": "Timeout", "latency_ms": int((time.monotonic() - start) * 1000), "kind": "server_error"}
    except httpx.HTTPError as exc:
        return {"alias": alias, "provider": provider, "model": model, "ok": False, "error": str(exc)[:200], "latency_ms": int((time.monotonic() - start) * 1000), "kind": "server_error"}


async def test_config(cfg: LLMConfig) -> list[dict]:
    """Ping each distinct (provider, model, plaintext key) combination once."""
    seen: set[tuple[str, str, str | None]] = set()
    results: list[dict] = []
    for t in cfg.triplets:
        key = security.decrypt_safe(t.api_key)
        sig = (t.provider, t.model, key)
        if sig in seen:
            continue
        seen.add(sig)
        results.append(
            await ping_triplet(alias=t.alias, provider=t.provider, model=t.model, encrypted_key=t.api_key)
        )
    return results
