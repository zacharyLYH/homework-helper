"""Pydantic models for the LLM config YAML DSL.

The unit of everything is an aliased ``provider:model:key`` triplet. Each of the
two operations (``chat``, ``memory``) then references triplets by alias in an
``order`` list and in optional ``when: reason`` routing rules.

Example DSL::

    version: 1
    name: My Config
    triplets:
      - alias: flash
        provider: gemini
        model: gemini-2.5-flash
        api_key: gAAAAAB...   # Fernet blob at rest, empty after export/import
      - alias: free
        provider: openrouter
        model: openrouter/free
        api_key: gAAAAAB...
    chat:
      order: [flash, free]
      rules:
        - when: rate_limit
          use: [free]
    memory:
      order: [flash]
"""

from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from app.llmconfig.catalog import PROVIDER_BY_ID, get_provider

CONFIG_VERSION = 1

# Predefined reasons a route may switch on. Keeping this list small is
# intentional: each new reason adds runtime branches and UI surface.
ROUTING_REASONS = ("rate_limit", "server_error")


class Triplet(BaseModel):
    alias: str
    provider: str
    model: str
    api_key: str = ""

    @field_validator("alias")
    @classmethod
    def _alias_not_blank(cls, v: str) -> str:
        alias = v.strip()
        if not alias:
            raise ValueError("Triplet alias cannot be blank")
        return alias


class RoutingRule(BaseModel):
    when: Literal["rate_limit", "server_error"]
    use: list[str]

    @field_validator("use")
    @classmethod
    def _use_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Routing rule 'use' cannot be empty")
        return v


class OperationConfig(BaseModel):
    order: list[str] = []
    rules: list[RoutingRule] = []


class LLMConfig(BaseModel):
    version: Literal[1] = CONFIG_VERSION
    name: str = "My Config"
    triplets: list[Triplet] = []
    chat: OperationConfig = OperationConfig()
    memory: OperationConfig = OperationConfig()

    @model_validator(mode="after")
    def _validate(self) -> "LLMConfig":
        aliases = [t.alias for t in self.triplets]
        if len(aliases) != len(set(aliases)):
            raise ValueError(f"Duplicate triplet aliases: {aliases}")

        for t in self.triplets:
            if not get_provider(t.provider):
                raise ValueError(
                    f"Unknown provider '{t.provider}'. "
                    f"Known providers: {sorted(PROVIDER_BY_ID)}"
                )

        alias_set = set(aliases)
        for section, op in (("chat", self.chat), ("memory", self.memory)):
            for ref in op.order:
                if ref not in alias_set:
                    raise ValueError(f"{section}.order references unknown triplet '{ref}'")
            for rule in op.rules:
                for ref in rule.use:
                    if ref not in alias_set:
                        raise ValueError(
                            f"{section} rule (when={rule.when}) references unknown triplet '{ref}'"
                        )
        return self
