"""Structured output schema models for memory LLM responses."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class ConceptUpsertPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_key: str = Field(
        description="Stable concept key in snake_case",
    )
    display_name: str = Field(
        description="Human-readable concept name",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names for the concept",
    )


class ConceptEdgePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_concept_key: str = Field(description="Source concept key")
    to_concept_key: str = Field(description="Target concept key")
    relation: str = Field(
        description='Edge relation. Must be one of "prerequisite" or "related".',
        pattern=r"^(prerequisite|related)$",
    )
    weight: Annotated[
        float,
        Field(ge=0.0, le=1.0, description="Relation confidence from 0.0 to 1.0"),
    ]


class ConceptStateDeltaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_key: str = Field(description="Concept key being updated")
    mastery: Annotated[
        float,
        Field(ge=0.0, le=1.0, description="Absolute mastery value from 0.0 to 1.0"),
    ]
    confidence: Annotated[
        float,
        Field(ge=0.0, le=1.0, description="Confidence in mastery estimate from 0.0 to 1.0"),
    ]


class MemoryEvaluationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skip: bool = Field(
        default=False,
        description="If true, no memory updates should be applied for this turn",
    )
    observations: list[str] = Field(
        default_factory=list,
        description="New evidence-backed learner observations",
    )
    concept_upserts: list[ConceptUpsertPayload] = Field(
        default_factory=list,
        description="Concept rows to insert or update",
    )
    concept_edges: list[ConceptEdgePayload] = Field(
        default_factory=list,
        description="Concept relationship edges",
    )
    concept_state_deltas: list[ConceptStateDeltaPayload] = Field(
        default_factory=list,
        description="Per-concept mastery updates",
    )
    trait_updates: dict[str, str] = Field(
        default_factory=dict,
        description="Stable learner trait key-value updates",
    )
    updated_summary: str = Field(
        default="",
        description="Replacement learner summary",
    )


def make_response_format_schema() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "memory_evaluation",
            "strict": True,
            "schema": MemoryEvaluationPayload.model_json_schema(),
        },
    }
