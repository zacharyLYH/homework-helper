"""Cross-cutting types shared by the ``app`` and ``memory`` packages.

Anything that crosses the app/memory boundary lives here so both sides
reference a single definition instead of parallel copies:

- Auth/ownership models used by both route sets (``User``, ``Subject``).
- Memory service <-> app contracts (``MemoryContext``, ``EnqueueDecision``,
  ``MemoryRuntimeStatus``, ``MemoryUpdatePayload``).
- Memory HTTP API shapes (``MemoryContextResponse``, ``MemoryJob``,
  ``MemoryJobsResponse``).

``app.schemas`` and ``memory.schemas`` re-export these for backward
compatibility; new code should import from here directly.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Shared DB models (used by app + memory routes)
# ---------------------------------------------------------------------------


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


class Subject(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Memory service <-> app contracts
# ---------------------------------------------------------------------------


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


class MemoryUpdatePayload(TypedDict):
    """Job payload written by the app's ``memory_updater`` and read by the
    memory worker. This dict is the app<->worker contract: it is serialized
    into ``memory_update_jobs.payload_json``."""

    trigger: str
    memory_loaded: bool
    memory_context: str
    messages: list[dict[str, str]]


# ---------------------------------------------------------------------------
# Memory HTTP API shapes
# ---------------------------------------------------------------------------


class MemoryContextResponse(BaseModel):
    subject_id: int
    user_id: int
    memory_context: str
    memory_loaded: bool


class MemoryJob(BaseModel):
    id: int
    status: str
    chat_id: int | None
    payload_json: str | None
    created_at: str
    updated_at: str


class MemoryJobsResponse(BaseModel):
    subject_id: int
    user_id: int
    jobs: list[MemoryJob]
