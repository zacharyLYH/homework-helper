import sqlite3
from dataclasses import dataclass
from pathlib import Path


REQUIRED_MEMORY_TABLES: tuple[str, ...] = (
    "concepts",
    "concept_aliases",
    "concept_edges",
    "learner_observations",
    "learner_concept_state",
    "learner_traits",
    "memory_versions",
    "memory_current",
    "memory_update_jobs",
    "retrieval_traces",
)

DEFAULT_MEMORY_DB_PATH = (Path(__file__).parent.parent.parent / "data" / "memory.db").resolve()


@dataclass(frozen=True)
class MemoryRuntimeStatus:
    requested: bool
    enabled: bool
    strict_mode: bool
    reason: str
    db_path: str


def _resolve_memory_db_path() -> Path:
    return DEFAULT_MEMORY_DB_PATH


def _missing_tables(db_path: Path) -> list[str]:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    table_names = {row[0] for row in rows}
    return [table for table in REQUIRED_MEMORY_TABLES if table not in table_names]


def get_memory_runtime_status(
    *,
    memory_enabled: bool,
    memory_strict_mode: bool,
) -> MemoryRuntimeStatus:
    db_path = _resolve_memory_db_path()

    if not memory_enabled:
        return MemoryRuntimeStatus(
            requested=False,
            enabled=False,
            strict_mode=memory_strict_mode,
            reason="disabled_by_config",
            db_path=str(db_path),
        )

    if not db_path.exists():
        return MemoryRuntimeStatus(
            requested=True,
            enabled=False,
            strict_mode=memory_strict_mode,
            reason="memory_db_missing",
            db_path=str(db_path),
        )

    try:
        missing = _missing_tables(db_path)
    except sqlite3.Error:
        return MemoryRuntimeStatus(
            requested=True,
            enabled=False,
            strict_mode=memory_strict_mode,
            reason="memory_db_unreadable",
            db_path=str(db_path),
        )

    if missing:
        return MemoryRuntimeStatus(
            requested=True,
            enabled=False,
            strict_mode=memory_strict_mode,
            reason="memory_schema_missing",
            db_path=str(db_path),
        )

    return MemoryRuntimeStatus(
        requested=True,
        enabled=True,
        strict_mode=memory_strict_mode,
        reason="memory_enabled",
        db_path=str(db_path),
    )


def enforce_memory_runtime(status: MemoryRuntimeStatus) -> None:
    if status.requested and not status.enabled and status.strict_mode:
        raise RuntimeError(
            f"Memory is enabled but unavailable ({status.reason}) at {status.db_path}."
        )
