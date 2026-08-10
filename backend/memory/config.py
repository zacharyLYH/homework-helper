import os
from pathlib import Path


REQUIRED_MEMORY_TABLES: tuple[str, ...] = (
    "concepts",
    "concept_edges",
    "learner_observations",
    "learner_concept_state",
    "learner_traits",
    "memory_summary",
    "memory_update_jobs",
    "retrieval_traces",
)

DEFAULT_MEMORY_DB_PATH = (
    Path(__file__).parent.parent.parent / "data" / "memory.db"
).resolve()


def resolve_memory_db_path() -> Path:
    configured_path = os.getenv("MEMORY_DATABASE_PATH", "").strip()
    if configured_path:
        return Path(configured_path).resolve()
    return DEFAULT_MEMORY_DB_PATH
