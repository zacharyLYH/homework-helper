"""Unit tests for the llmconfig package (Task 1)."""

import pytest

from app.db import get_conn
from app.llmconfig import parser, security, store
from app.llmconfig.model import LLMConfig
from app.llmconfig.parser import LLMConfigError, empty_config


def _valid_ui() -> dict:
    """The config as the UI would submit it: plaintext keys."""
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


def _valid_cfg() -> LLMConfig:
    """A config as stored in the DB: keys encrypted."""
    return parser.apply_incoming(_valid_ui(), None)


def _valid_yaml() -> str:
    return parser.serialize_config(_valid_cfg())


# --- security ---


def test_encrypt_decrypt_roundtrip() -> None:
    token = security.encrypt("sk-my-secret")
    assert token != "sk-my-secret"
    assert security.decrypt(token) == "sk-my-secret"


def test_encrypt_empty_stays_empty() -> None:
    assert security.encrypt("") == ""
    assert security.decrypt("") == ""


def test_decrypt_garbage_raises() -> None:
    with pytest.raises(ValueError):
        security.decrypt("not-a-fernet-token")


def test_decrypt_safe_returns_none_on_garbage() -> None:
    assert security.decrypt_safe("not-a-fernet-token") is None
    assert security.decrypt_safe("") is None


def test_mask_key() -> None:
    assert security.mask_key("sk-flash-secret") == "sk-f****cret"
    assert security.mask_key("") == ""
    assert security.mask_key("short") == "****"


def test_missing_secret_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.llmconfig import security as sec

    monkeypatch.setattr(sec.settings, "aes_secret_key", "")
    sec._fernet.cache_clear()
    try:
        with pytest.raises(sec.MissingSecretKeyError):
            sec.encrypt("sk-x")
    finally:
        sec._fernet.cache_clear()


# --- model validation ---


def test_parse_valid_yaml() -> None:
    cfg = parser.parse_config(_valid_yaml())
    assert cfg.name == "My Config"
    assert [t.alias for t in cfg.triplets] == ["flash", "free"]
    assert cfg.chat.order == ["flash", "free"]
    assert cfg.chat.rules[0].when == "rate_limit"
    assert cfg.chat.rules[0].use == ["free"]
    assert cfg.memory.order == ["flash"]


def test_parse_blank_returns_empty() -> None:
    cfg = parser.parse_config("")
    assert cfg.triplets == []
    assert cfg.chat.order == []
    assert cfg.memory.order == []


def test_parse_invalid_yaml_raises() -> None:
    with pytest.raises(LLMConfigError, match="Invalid YAML"):
        parser.parse_config("{a: b")


def test_parse_non_mapping_raises() -> None:
    with pytest.raises(LLMConfigError, match="must be a mapping"):
        parser.parse_config("- just\n- a\n- list\n")


def test_duplicate_alias_rejected() -> None:
    ui = _valid_ui()
    ui["triplets"][1]["alias"] = "flash"
    with pytest.raises(LLMConfigError, match="Duplicate triplet aliases"):
        parser.apply_incoming(ui, None)


def test_unknown_provider_rejected() -> None:
    ui = _valid_ui()
    ui["triplets"][1]["provider"] = "skynet"
    with pytest.raises(LLMConfigError, match="Unknown provider"):
        parser.apply_incoming(ui, None)


def test_unknown_ref_in_order_rejected() -> None:
    ui = _valid_ui()
    ui["chat"]["order"] = ["flash", "nope"]
    with pytest.raises(LLMConfigError, match="references unknown triplet 'nope'"):
        parser.apply_incoming(ui, None)


def test_unknown_ref_in_rule_rejected() -> None:
    ui = _valid_ui()
    ui["chat"]["rules"][0]["use"] = ["nope"]
    with pytest.raises(LLMConfigError, match="references unknown triplet 'nope'"):
        parser.apply_incoming(ui, None)


def test_invalid_rule_reason_rejected() -> None:
    ui = _valid_ui()
    ui["chat"]["rules"][0]["when"] = "budget_exceeded"
    with pytest.raises(LLMConfigError):
        parser.apply_incoming(ui, None)


# --- serialize / export / import ---


def test_serialize_roundtrip_preserves_encrypted_keys() -> None:
    cfg = _valid_cfg()
    cfg2 = parser.parse_config(_valid_yaml())
    assert cfg2.name == cfg.name
    assert [t.alias for t in cfg2.triplets] == [t.alias for t in cfg.triplets]
    assert cfg2.chat == cfg.chat
    assert cfg2.memory == cfg.memory
    assert cfg2.triplets[0].api_key != "sk-flash-secret"
    assert security.decrypt(cfg2.triplets[0].api_key) == "sk-flash-secret"


def test_export_wipes_keys() -> None:
    exported = parser.export_config(_valid_cfg())
    assert "sk-flash-secret" not in exported
    assert "__REPLACE_ME__" in exported
    reimported = parser.import_config(exported)
    assert all(t.api_key == "" for t in reimported.triplets)
    assert reimported.triplets[0].alias == "flash"


def test_to_ui_json_masks_keys() -> None:
    ui = parser.to_ui_json(_valid_cfg())
    assert ui["triplets"][0]["api_key"] == "sk-f****cret"
    assert ui["triplets"][0]["has_key"] is True
    assert "sk-flash-secret" not in ui["triplets"][0]["api_key"]


def test_apply_incoming_keeps_existing_key_when_masked() -> None:
    current = _valid_cfg()
    ui = parser.to_ui_json(current)
    incoming = parser.apply_incoming(ui, current)
    assert incoming.triplets[0].api_key == current.triplets[0].api_key
    assert security.decrypt(incoming.triplets[0].api_key) == "sk-flash-secret"


def test_apply_incoming_keeps_existing_key_when_empty() -> None:
    current = _valid_cfg()
    ui = parser.to_ui_json(current)
    ui["triplets"][0]["api_key"] = ""
    incoming = parser.apply_incoming(ui, current)
    assert incoming.triplets[0].api_key == current.triplets[0].api_key


def test_apply_incoming_encrypts_changed_key() -> None:
    current = _valid_cfg()
    ui = parser.to_ui_json(current)
    ui["triplets"][0]["api_key"] = "sk-brand-new"
    incoming = parser.apply_incoming(ui, current)
    assert security.decrypt(incoming.triplets[0].api_key) == "sk-brand-new"


def test_apply_incoming_new_triplet_encrypts_raw_key() -> None:
    ui = _valid_ui()
    ui["triplets"].append(
        {"alias": "pro", "provider": "gemini", "model": "gemini-2.5-pro", "api_key": "sk-pro"}
    )
    incoming = parser.apply_incoming(ui, None)
    assert security.decrypt(incoming.triplets[-1].api_key) == "sk-pro"


def test_apply_incoming_new_triplet_without_key_stays_empty() -> None:
    current = _valid_cfg()
    ui = parser.to_ui_json(current)
    ui["triplets"].append(
        {"alias": "pro", "provider": "gemini", "model": "gemini-2.5-pro", "api_key": ""}
    )
    incoming = parser.apply_incoming(ui, current)
    assert incoming.triplets[-1].api_key == ""


def test_empty_config_roundtrips() -> None:
    cfg = empty_config()
    yaml_text = parser.serialize_config(cfg)
    assert parser.parse_config(yaml_text) == cfg


# --- store ---


def test_store_roundtrip(setup_test_db, seed) -> None:
    seed(users=["alice@school.edu"])
    with get_conn() as conn:
        user_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("alice@school.edu",)
        ).fetchone()["id"]

    assert store.get_config(user_id) is None

    cfg = _valid_cfg()
    store.save_config(user_id, cfg)
    loaded = store.get_config(user_id)
    assert loaded is not None
    assert loaded == cfg
    assert security.decrypt(loaded.triplets[0].api_key) == "sk-flash-secret"
