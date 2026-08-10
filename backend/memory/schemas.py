from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryRuntimeStatus:
    requested: bool
    enabled: bool
    strict_mode: bool
    reason: str
    db_path: str


@dataclass(frozen=True)
class MemoryContext:
    summary: str
    traits: dict[str, str]
    weak_concepts: list[tuple[str, float]]  # (display_name, mastery)
    prerequisites: list[tuple[str, str]]     # (from_display, to_display)
    recent_observations: list[str]
    rendered: str

    @property
    def is_empty(self) -> bool:
        return not self.rendered.strip()


@dataclass(frozen=True)
class EnqueueDecision:
    enqueued: bool
    job_id: int | None
    reason: str
