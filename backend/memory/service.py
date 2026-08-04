import sqlite3

from memory.config import resolve_memory_db_path
from memory.db import missing_required_tables
from memory.schemas import MemoryRuntimeStatus


def get_memory_runtime_status(
    *,
    memory_enabled: bool,
    memory_strict_mode: bool,
) -> MemoryRuntimeStatus:
    db_path = resolve_memory_db_path()

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
        missing = missing_required_tables(db_path)
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
