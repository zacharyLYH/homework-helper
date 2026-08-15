"""Persistence of a user's LLM config.

The whole config is one YAML string on the ``users.llm_config_yaml`` column. No
tables of their own — the import/export parser is the source of truth for
structure, and this module only does dumb read/write of the string.
"""

from app.db import get_user_llm_config_yaml, save_user_llm_config_yaml
from app.llmconfig.parser import parse_config, serialize_config
from app.llmconfig.model import LLMConfig


def get_config(user_id: int | None) -> LLMConfig | None:
    yaml_text = get_user_llm_config_yaml(user_id)
    if not yaml_text:
        return None
    return parse_config(yaml_text)


def save_config(user_id: int, cfg: LLMConfig) -> None:
    save_user_llm_config_yaml(user_id, serialize_config(cfg))
