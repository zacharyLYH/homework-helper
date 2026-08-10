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

# Service layer config
MEMORY_MIN_TURN_CHARS: int = int(os.getenv("MEMORY_MIN_TURN_CHARS", "20"))
MEMORY_DEDUP_WINDOW_SECONDS: int = int(os.getenv("MEMORY_DEDUP_WINDOW_SECONDS", "30"))
MEMORY_MAX_JOBS_PER_HOUR: int = int(os.getenv("MEMORY_MAX_JOBS_PER_HOUR", "60"))
MEMORY_WEAK_MASTERY_THRESHOLD: float = float(os.getenv("MEMORY_WEAK_MASTERY_THRESHOLD", "0.5"))
MEMORY_WEAK_CONCEPTS_LIMIT: int = int(os.getenv("MEMORY_WEAK_CONCEPTS_LIMIT", "5"))
MEMORY_RECENT_OBS_LIMIT: int = int(os.getenv("MEMORY_RECENT_OBS_LIMIT", "3"))


def resolve_memory_db_path() -> Path:
    configured_path = os.getenv("MEMORY_DATABASE_PATH", "").strip()
    if configured_path:
        return Path(configured_path).resolve()
    return DEFAULT_MEMORY_DB_PATH
