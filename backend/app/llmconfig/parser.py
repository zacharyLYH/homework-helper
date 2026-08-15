"""YAML <-> model serialization, import/export, and UI-facing key handling.

This is the single YAML code path. The UI never sees YAML or encrypted blobs:
it exchanges JSON with masked keys, and the DB stores the YAML string produced
here. Export/import reuse the same parser so what you share is exactly what you
save (minus the secrets).
"""

from pydantic import ValidationError
from yaml import safe_dump, safe_load

from app.llmconfig import security
from app.llmconfig.model import LLMConfig

# Used as a placeholder in exported/imported YAML so it is obvious the secret
# must be re-entered. Not a real key format.
EXPORT_PLACEHOLDER = "__REPLACE_ME__"


class LLMConfigError(ValueError):
    """Raised when a config (JSON or YAML) fails validation."""


def parse_config(yaml_text: str) -> LLMConfig:
    """Parse a YAML string into a validated :class:`LLMConfig`."""
    if not yaml_text or not yaml_text.strip():
        return empty_config()
    try:
        data = safe_load(yaml_text)
    except Exception as exc:
        raise LLMConfigError(f"Invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMConfigError("Config YAML must be a mapping")
    return _model_from_dict(data)


def _model_from_dict(data: dict) -> LLMConfig:
    try:
        cfg = LLMConfig.model_validate(data)
    except ValidationError as exc:
        raise LLMConfigError(_format_errors(exc)) from exc
    return cfg


def _format_errors(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        lines.append(f"{loc}: {err['msg']}")
    return "; ".join(lines) or "Invalid config"


def serialize_config(cfg: LLMConfig, *, wipe_keys: bool = False) -> str:
    """Serialize to YAML. With ``wipe_keys`` the stored secrets are replaced by
    a placeholder (used for export)."""
    data = cfg.model_dump()
    if wipe_keys:
        for t in data["triplets"]:
            t["api_key"] = EXPORT_PLACEHOLDER if t["api_key"] else ""
    return safe_dump(data, sort_keys=False, default_flow_style=False).strip() + "\n"


def export_config(cfg: LLMConfig) -> str:
    return serialize_config(cfg, wipe_keys=True)


def import_config(yaml_text: str) -> LLMConfig:
    """Parse shared YAML and drop any key material so the importing user must
    supply their own secrets."""
    cfg = parse_config(yaml_text)
    for t in cfg.triplets:
        t.api_key = ""
    return cfg


def empty_config() -> LLMConfig:
    return LLMConfig(triplets=[])


def to_ui_json(cfg: LLMConfig) -> dict:
    """JSON payload for the UI: secrets replaced by a masked preview."""
    data = cfg.model_dump()
    for t in data["triplets"]:
        plain = security.decrypt_safe(t["api_key"])
        t["api_key"] = security.mask_key(plain) if plain is not None else ""
        t["has_key"] = bool(plain)
    return data


def apply_incoming(data: dict, current: LLMConfig | None) -> LLMConfig:
    """Merge an edited config from the UI onto the currently stored one.

    Incoming triplet keys are either a raw new secret, a masked preview of the
    stored secret, or empty. We keep the existing encrypted blob when the key
    was left untouched; otherwise we encrypt the new value.
    """
    incoming = _model_from_dict(data)
    existing_by_alias = {t.alias: t for t in current.triplets} if current else {}

    for t in incoming.triplets:
        existing = existing_by_alias.get(t.alias)
        if not t.api_key:
            if existing is not None:
                t.api_key = existing.api_key
            continue
        if existing is not None:
            existing_plain = security.decrypt_safe(existing.api_key)
            if existing_plain is not None and t.api_key == security.mask_key(existing_plain):
                t.api_key = existing.api_key
                continue
        t.api_key = security.encrypt(t.api_key)

    return incoming
