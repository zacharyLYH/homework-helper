"""Tests for the settings API routes and ping helper."""

import httpx
import pytest

from app.llmconfig import security
from app.llmconfig.ping import ping_triplet


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _valid_body() -> dict:
    return {
        "version": 1,
        "name": "My Config",
        "triplets": [
            {"alias": "flash", "provider": "gemini", "model": "gemini-2.5-flash", "api_key": "sk-flash-secret"},
            {"alias": "free", "provider": "openrouter", "model": "openrouter/free", "api_key": "sk-free-secret"},
        ],
        "chat": {"order": ["flash", "free"], "rules": [{"when": "rate_limit", "use": ["free"]}]},
        "memory": {"order": ["flash"], "rules": []},
    }


# --- routes ---


async def test_get_config_empty_for_new_user(client, auth_token) -> None:
    res = await client.get("/api/settings/config", headers=_headers(auth_token()))
    assert res.status_code == 200
    body = res.json()
    assert body["triplets"] == []
    assert body["chat"]["order"] == []
    assert body["memory"]["order"] == []


async def test_requires_auth(client) -> None:
    res = await client.get("/api/settings/config")
    assert res.status_code == 401


async def test_put_and_get_roundtrip(client, auth_token) -> None:
    put = await client.put("/api/settings/config", json=_valid_body(), headers=_headers(auth_token()))
    assert put.status_code == 200
    saved = put.json()
    assert saved["triplets"][0]["api_key"] == "sk-f****cret"
    assert saved["triplets"][0]["has_key"] is True
    assert "sk-flash-secret" not in saved["triplets"][0]["api_key"]

    got = await client.get("/api/settings/config", headers=_headers(auth_token()))
    assert got.status_code == 200
    assert got.json() == saved


async def test_put_invalid_config_returns_422(client, auth_token) -> None:
    body = _valid_body()
    body["chat"]["order"] = ["flash", "nope"]
    res = await client.put("/api/settings/config", json=body, headers=_headers(auth_token()))
    assert res.status_code == 422
    assert "unknown triplet 'nope'" in res.json()["detail"]


async def test_export_returns_yaml_with_placeholders(client, auth_token) -> None:
    await client.put("/api/settings/config", json=_valid_body(), headers=_headers(auth_token()))
    res = await client.post("/api/settings/config/export", headers=_headers(auth_token()))
    assert res.status_code == 200
    yaml_text = res.json()["yaml"]
    assert "__REPLACE_ME__" in yaml_text
    assert "sk-flash-secret" not in yaml_text


async def test_export_without_config_returns_404(client, auth_token) -> None:
    res = await client.post("/api/settings/config/export", headers=_headers(auth_token()))
    assert res.status_code == 404


async def test_import_returns_config_with_empty_keys(client, auth_token) -> None:
    exported = await client.post(
        "/api/settings/config/export",
        headers=_headers(auth_token()),
    )
    if exported.status_code == 404:
        # seed a config first
        await client.put("/api/settings/config", json=_valid_body(), headers=_headers(auth_token()))
        exported = await client.post("/api/settings/config/export", headers=_headers(auth_token()))
    yaml_text = exported.json()["yaml"]

    res = await client.post("/api/settings/config/import", json={"yaml": yaml_text}, headers=_headers(auth_token()))
    assert res.status_code == 200
    body = res.json()
    assert [t["alias"] for t in body["triplets"]] == ["flash", "free"]
    assert all(t["api_key"] == "" and t["has_key"] is False for t in body["triplets"])


async def test_import_invalid_yaml_returns_422(client, auth_token) -> None:
    res = await client.post("/api/settings/config/import", json={"yaml": "{a: b"}, headers=_headers(auth_token()))
    assert res.status_code == 422


async def test_put_without_aes_secret_returns_500(client, auth_token, monkeypatch) -> None:
    from app.llmconfig import security

    def boom(value: str) -> str:
        raise security.MissingSecretKeyError("AES_SECRET_KEY is not set")

    monkeypatch.setattr(security, "encrypt", boom)
    res = await client.put("/api/settings/config", json=_valid_body(), headers=_headers(auth_token()))
    assert res.status_code == 500
    assert "AES_SECRET_KEY" in res.json()["detail"]


async def test_catalog(client, auth_token) -> None:
    res = await client.get("/api/settings/catalog", headers=_headers(auth_token()))
    assert res.status_code == 200
    body = res.json()
    providers = body["providers"]
    provider_ids = {p["id"] for p in providers}
    assert "gemini" in provider_ids and "openrouter" in provider_ids
    # every provider has a key page so first-time users can get a key
    assert all(p["key_url"].startswith("http") for p in providers)
    models = body["models"]
    assert any(m["provider"] == "gemini" and m["id"] == "gemini-3.7-flash" for m in models)
    # every model exposes purpose, tier, cost, and image capability
    for m in models:
        assert m["recommended"] in ("chat", "memory", "either")
        assert m["tier"] in ("premium", "standard", "budget", "free")
        assert m["price_in"] and m["price_out"]
    # anything usable for chat must accept images (homework photos)
    chat_models = [m for m in models if m["recommended"] in ("chat", "either")]
    assert chat_models and all(m["supports_images"] for m in chat_models)
    # free tier: one image-capable model and one text-only model
    free_models = [m for m in models if m["tier"] == "free"]
    assert any(m["supports_images"] for m in free_models)
    assert any(not m["supports_images"] for m in free_models)
    # memory options include cheap text-only models
    memory_models = [m for m in models if m["recommended"] == "memory"]
    assert any(not m["supports_images"] for m in memory_models)


async def test_test_endpoint_returns_results(client, auth_token, monkeypatch) -> None:
    await client.put("/api/settings/config", json=_valid_body(), headers=_headers(auth_token()))

    async def fake_tests(cfg):
        return [{"alias": "flash", "ok": True, "latency_ms": 42}]

    monkeypatch.setattr("app.routes.settings.run_config_tests", fake_tests)
    res = await client.post("/api/settings/config/test", headers=_headers(auth_token()))
    assert res.status_code == 200
    results = res.json()["results"]
    assert results[0]["alias"] == "flash"
    assert results[0]["ok"] is True
    assert results[0]["latency_ms"] == 42


async def test_test_endpoint_accepts_unsaved_config(client, auth_token, monkeypatch) -> None:
    """The UI can test a freshly-created model before it is saved."""
    captured = {}

    async def fake_tests(cfg):
        captured["cfg"] = cfg
        return [{"alias": "flash", "ok": True, "latency_ms": 42}]

    monkeypatch.setattr("app.routes.settings.run_config_tests", fake_tests)
    res = await client.post(
        "/api/settings/config/test",
        json=_valid_body(),
        headers=_headers(auth_token()),
    )
    assert res.status_code == 200
    results = res.json()["results"]
    assert results[0]["alias"] == "flash"
    assert results[0]["ok"] is True
    assert results[0]["latency_ms"] == 42
    # the submitted config was parsed (keys encrypted) and pinged
    assert [t.alias for t in captured["cfg"].triplets] == ["flash", "free"]
    assert security.decrypt(captured["cfg"].triplets[0].api_key) == "sk-flash-secret"


async def test_test_endpoint_invalid_body_returns_422(client, auth_token) -> None:
    body = _valid_body()
    body["chat"]["order"] = ["flash", "nope"]
    res = await client.post("/api/settings/config/test", json=body, headers=_headers(auth_token()))
    assert res.status_code == 422


async def test_test_endpoint_without_config_returns_404(client, auth_token) -> None:
    res = await client.post("/api/settings/config/test", headers=_headers(auth_token()))
    assert res.status_code == 404


# --- ping helper ---


def _encrypted_key() -> str:
    return security.encrypt("sk-test-key")


def _mock_transport(status_code: int, text: str = "") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=text)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_ping_success() -> None:
    result = await ping_triplet(
        alias="flash",
        provider="gemini",
        model="gemini-2.5-flash",
        encrypted_key=_encrypted_key(),
        transport=_mock_transport(200, '{"id":"x"}'),
    )
    assert result["ok"] is True
    assert result["latency_ms"] is not None
    assert result["kind"] == "ok"


@pytest.mark.asyncio
async def test_ping_rate_limit() -> None:
    result = await ping_triplet(
        alias="flash", provider="gemini", model="gemini-2.5-flash",
        encrypted_key=_encrypted_key(), transport=_mock_transport(429, "quota"),
    )
    assert result["ok"] is False
    assert result["kind"] == "rate_limit"


@pytest.mark.asyncio
async def test_ping_server_error() -> None:
    result = await ping_triplet(
        alias="flash", provider="gemini", model="gemini-2.5-flash",
        encrypted_key=_encrypted_key(), transport=_mock_transport(500, "boom"),
    )
    assert result["ok"] is False
    assert result["kind"] == "server_error"


@pytest.mark.asyncio
async def test_ping_missing_key() -> None:
    result = await ping_triplet(
        alias="flash", provider="gemini", model="gemini-2.5-flash",
        encrypted_key="", transport=_mock_transport(200, "{}"),
    )
    assert result["ok"] is False
    assert result["error"] == "Missing API key"


@pytest.mark.asyncio
async def test_ping_unknown_provider() -> None:
    result = await ping_triplet(
        alias="x", provider="skynet", model="t-800",
        encrypted_key=_encrypted_key(), transport=_mock_transport(200, "{}"),
    )
    assert result["ok"] is False
    assert "Unknown provider" in result["error"]


@pytest.mark.asyncio
async def test_ping_timeout() -> None:
    def hang(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    result = await ping_triplet(
        alias="flash", provider="gemini", model="gemini-2.5-flash",
        encrypted_key=_encrypted_key(), transport=httpx.MockTransport(hang),
    )
    assert result["ok"] is False
