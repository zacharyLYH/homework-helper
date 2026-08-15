from dataclasses import dataclass, field

from shared.schemas import EnqueueDecision, MemoryContext, MemoryRuntimeStatus


# ---------------------------------------------------------------------------
# LLM evaluation contract (memory-internal)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConceptUpsert:
    concept_key: str
    display_name: str
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConceptEdgeUpsert:
    from_concept_key: str
    to_concept_key: str
    relation: str  # "prerequisite" | "related"
    weight: float


@dataclass(frozen=True)
class ConceptStateDelta:
    concept_key: str
    mastery: float     # absolute new value 0.0–1.0
    confidence: float  # absolute new value 0.0–1.0


@dataclass(frozen=True)
class MemoryEvaluation:
    skip: bool
    observations: list[str]
    concept_upserts: list[ConceptUpsert]
    concept_edges: list[ConceptEdgeUpsert]
    concept_state_deltas: list[ConceptStateDelta]
    trait_updates: dict[str, str]
    updated_summary: str


@dataclass(frozen=True)
class MemoryEvaluationInput:
    user_id: int
    subject_id: int
    turn_snippet: list[dict]                    # last N messages (role + content)
    current_summary: str
    current_traits: dict[str, str]
    current_weak_concepts: list[tuple[str, float]]  # (display_name, mastery)
