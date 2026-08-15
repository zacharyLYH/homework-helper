"""Async LLM client for memory evaluation.

Single public function: ``evaluate_memory``.
Handles LLM call, structural parse/validation, and raises on failure so the
caller (worker) can mark the job failed and preserve the raw response.
"""

from __future__ import annotations

import asyncio
import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.config import settings
from app.logging import get_logger
from memory.config import MEMORY_LLM_MODEL, MEMORY_LLM_TIMEOUT_SECONDS
from memory.prompts import SYSTEM_PROMPT, render_user_prompt
from memory.schemas import (
    ConceptEdgeUpsert,
    ConceptStateDelta,
    ConceptUpsert,
    MemoryEvaluation,
    MemoryEvaluationInput,
)

log = get_logger(__name__)

_ALLOWED_RELATIONS = frozenset({"prerequisite", "related"})


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
    return ChatOpenAI(
        base_url=base_url,
        api_key=SecretStr(api_key) if api_key else SecretStr(""),
        model=model,
        temperature=0.0,
        # reasoning models burn most of the budget on internal thought; give headroom
        max_completion_tokens=4096,
        model_kwargs={
            "response_format": {"type": "json_object"},
        },
    )


def _parse_evaluation(raw: str) -> MemoryEvaluation:
    """Parse and structurally validate LLM JSON output into MemoryEvaluation.

    Raises ValueError / KeyError / json.JSONDecodeError on any structural problem.
    """
    data: dict = json.loads(raw)

    skip = bool(data.get("skip", False))
    observations = [str(o) for o in data.get("observations", [])]

    concept_upserts = [
        ConceptUpsert(
            concept_key=str(c["concept_key"]),
            display_name=str(c["display_name"]),
            aliases=[str(a) for a in c.get("aliases", [])],
        )
        for c in data.get("concept_upserts", [])
    ]

    concept_edges: list[ConceptEdgeUpsert] = []
    for e in data.get("concept_edges", []):
        relation = str(e.get("relation", ""))
        if relation not in _ALLOWED_RELATIONS:
            raise ValueError(f"Invalid relation: {relation!r}")
        weight = float(e["weight"])
        if not 0.0 <= weight <= 1.0:
            raise ValueError(f"Edge weight out of range: {weight}")
        concept_edges.append(
            ConceptEdgeUpsert(
                from_concept_key=str(e["from_concept_key"]),
                to_concept_key=str(e["to_concept_key"]),
                relation=relation,
                weight=weight,
            )
        )

    concept_state_deltas: list[ConceptStateDelta] = []
    for d in data.get("concept_state_deltas", []):
        mastery = float(d["mastery"])
        confidence = float(d["confidence"])
        if not 0.0 <= mastery <= 1.0:
            raise ValueError(f"Mastery out of range: {mastery}")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Confidence out of range: {confidence}")
        concept_state_deltas.append(
            ConceptStateDelta(
                concept_key=str(d["concept_key"]),
                mastery=mastery,
                confidence=confidence,
            )
        )

    trait_updates = {str(k): str(v) for k, v in data.get("trait_updates", {}).items()}
    updated_summary = str(data.get("updated_summary", ""))

    return MemoryEvaluation(
        skip=skip,
        observations=observations,
        concept_upserts=concept_upserts,
        concept_edges=concept_edges,
        concept_state_deltas=concept_state_deltas,
        trait_updates=trait_updates,
        updated_summary=updated_summary,
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
    return _parse_evaluation(raw)
