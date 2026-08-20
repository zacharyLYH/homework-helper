"""Async LLM client for memory evaluation.

Single public function: ``evaluate_memory``.
Handles LLM call, structural parse/validation, and raises on failure so the
caller (worker) can mark the job failed and preserve the raw response.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.config import settings
from app.logging import get_logger
from memory.config import MEMORY_LLM_MODEL, MEMORY_LLM_TIMEOUT_SECONDS
from memory.prompts import SYSTEM_PROMPT, render_user_prompt
from memory.llm_schema import MemoryEvaluationPayload, make_response_format_schema
from memory.schemas import (
    ConceptEdgeUpsert,
    ConceptStateDelta,
    ConceptUpsert,
    MemoryEvaluation,
    MemoryEvaluationInput,
)

log = get_logger(__name__)


def _make_response_format_schema() -> dict[str, Any]:
    return make_response_format_schema()


def _resolve_memory_llm(user_id: int | None) -> tuple[str, str, str] | None:
    """Resolve (base_url, api_key, model) from the user's memory config.

    Returns ``None`` when the user has no usable memory operand so callers
    fall back to the global default LLM.
    """
    from app.llmconfig import security, store
    from app.llmconfig.catalog import get_provider

    cfg = store.get_config(user_id)
    if cfg is None or not cfg.memory.order:
        return None
    by_alias = {t.alias: t for t in cfg.triplets}
    for alias in cfg.memory.order:
        triplet = by_alias.get(alias)
        if triplet is None:
            continue
        provider = get_provider(triplet.provider)
        key = security.decrypt_safe(triplet.api_key)
        if provider is not None and key is not None:
            return provider.base_url, key, triplet.model
    return None


def _make_llm(*, base_url: str, api_key: str, model: str) -> ChatOpenAI:
    model_kwargs: dict[str, Any] = {
        "response_format": _make_response_format_schema(),
    }
    if "openrouter.ai" in base_url:
        model_kwargs["provider"] = {"require_parameters": True}

    return ChatOpenAI(
        base_url=base_url,
        api_key=SecretStr(api_key) if api_key else SecretStr(""),
        model=model,
        temperature=0.0,
        # reasoning models burn most of the budget on internal thought; give headroom
        max_completion_tokens=4096,
        model_kwargs=model_kwargs,
    )


def _content_to_data(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content

    if isinstance(content, str):
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("LLM response JSON must be an object")
        return data

    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(str(part.get("text", "")))
        if not text_parts:
            raise ValueError("LLM response content list did not contain text parts")
        data = json.loads("".join(text_parts))
        if not isinstance(data, dict):
            raise ValueError("LLM response JSON must be an object")
        return data

    raise TypeError(f"Unsupported LLM response content type: {type(content)!r}")


def _parse_evaluation(content: Any) -> MemoryEvaluation:
    """Parse and structurally validate LLM JSON output into MemoryEvaluation.

    Raises ValueError / KeyError / json.JSONDecodeError on any structural problem.
    """
    data = _content_to_data(content)
    parsed = MemoryEvaluationPayload.model_validate(data)

    return MemoryEvaluation(
        skip=parsed.skip,
        observations=parsed.observations,
        concept_upserts=[
            ConceptUpsert(
                concept_key=item.concept_key,
                display_name=item.display_name,
                aliases=item.aliases,
            )
            for item in parsed.concept_upserts
        ],
        concept_edges=[
            ConceptEdgeUpsert(
                from_concept_key=item.from_concept_key,
                to_concept_key=item.to_concept_key,
                relation=item.relation,
                weight=float(item.weight),
            )
            for item in parsed.concept_edges
        ],
        concept_state_deltas=[
            ConceptStateDelta(
                concept_key=item.concept_key,
                mastery=float(item.mastery),
                confidence=float(item.confidence),
            )
            for item in parsed.concept_state_deltas
        ],
        trait_updates=parsed.trait_updates,
        updated_summary=parsed.updated_summary,
    )


async def evaluate_memory(
    *,
    current_state: MemoryEvaluationInput,
) -> MemoryEvaluation:
    """Call LLM to evaluate a memory turn. Raises on LLM error or bad output."""
    user_prompt = render_user_prompt(current_state=current_state)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    log.info(
        "Memory LLM request — system_prompt=%r user_prompt=%r",
        SYSTEM_PROMPT,
        user_prompt[:3000],
    )

    resolved = _resolve_memory_llm(current_state.user_id)
    if resolved is not None:
        base_url, api_key, model = resolved
    else:
        base_url = settings.openrouter_base_url
        api_key = settings.openrouter_api_key if settings.openrouter_api_key else ""
        model = MEMORY_LLM_MODEL

    llm = _make_llm(base_url=base_url, api_key=api_key, model=model)
    response = await asyncio.wait_for(
        llm.ainvoke(messages),
        timeout=MEMORY_LLM_TIMEOUT_SECONDS,
    )

    raw = str(response.content)
    log.info("Memory LLM response — raw=%r", raw[:3000])
    return _parse_evaluation(response.content)
