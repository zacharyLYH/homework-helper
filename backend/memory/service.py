import json
import sqlite3

from memory.config import resolve_memory_db_path
from memory.db import get_conn
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


def load_memory_context(*, user_id: int, subject_id: int) -> str:
    """Return current summary or latest observations for a learner scope."""
    rows: list[sqlite3.Row] = []
    with get_conn() as conn:
        current = conn.execute(
            """
            SELECT summary
            FROM memory_summary
            WHERE user_id = ? AND subject_id = ?
            LIMIT 1
            """,
            (user_id, subject_id),
        ).fetchone()
        if current and current["summary"]:
            return str(current["summary"])

        rows = conn.execute(
            """
            SELECT observation
            FROM learner_observations
            WHERE user_id = ? AND subject_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 3
            """,
            (user_id, subject_id),
        ).fetchall()

    if not rows:
        return ""

    observations = [
        str(row["observation"]).strip() for row in rows if row["observation"]
    ]
    if not observations:
        return ""

    bullet_points = "\n".join(f"- {item}" for item in observations)
    return f"Recent learner observations:\n{bullet_points}"


def enqueue_memory_update(
    *,
    user_id: int,
    subject_id: int,
    chat_id: int | None,
    payload: dict,
) -> int:
    lastrowid: int | None = None
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO memory_update_jobs (
                user_id,
                subject_id,
                chat_id,
                status,
                payload_json,
                updated_at
            ) VALUES (?, ?, ?, 'pending', ?, datetime('now'))
            """,
            (user_id, subject_id, chat_id, json.dumps(payload)),
        )
        lastrowid = cur.lastrowid

    if lastrowid is None:
        raise RuntimeError("Failed to enqueue memory update job")

    return int(lastrowid)
