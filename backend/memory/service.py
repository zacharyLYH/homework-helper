"""Memory service layer: synchronous skip logic and context loading.

Functions:
  - get_memory_runtime_status: Check if memory DB is ready
  - enforce_memory_runtime: Raise if memory is required but unavailable
  - load_memory_context: Assemble multi-section context for agent prompt
  - enqueue_memory_update: Decide whether to enqueue a worker job (with skip heuristics)
"""

import json
import sqlite3
import time
from typing import Any

from app.structured_log import structured_log
from memory.config import (
    MEMORY_DEDUP_WINDOW_SECONDS,
    MEMORY_MAX_JOBS_PER_HOUR,
    MEMORY_MIN_TURN_CHARS,
    MEMORY_RECENT_OBS_LIMIT,
    MEMORY_WEAK_CONCEPTS_LIMIT,
    MEMORY_WEAK_MASTERY_THRESHOLD,
    resolve_memory_db_path,
)
from memory.db import get_conn
from memory.db import missing_required_tables
from memory.schemas import EnqueueDecision
from memory.schemas import MemoryContext
from memory.schemas import MemoryRuntimeStatus


# ============================================================================
# Memory Runtime Status
# ============================================================================


def get_memory_runtime_status(
    *,
    memory_enabled: bool,
    memory_strict_mode: bool,
) -> MemoryRuntimeStatus:
    """Check if memory database is available and properly initialized."""
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
    """Raise if memory is required but unavailable."""
    if status.requested and not status.enabled and status.strict_mode:
        raise RuntimeError(
            f"Memory is enabled but unavailable ({status.reason}) at {status.db_path}."
        )


# ============================================================================
# Context Loading
# ============================================================================


def load_memory_context(*, user_id: int, subject_id: int) -> MemoryContext:
    """Load multi-section context for the agent prompt.
    
    Reads from memory_summary, learner_traits, learner_concept_state,
    concept_edges, and learner_observations. Logs all retrievals to
    retrieval_traces for observability.
    
    Returns a MemoryContext with summary, traits, weak concepts, prerequisites,
    and recent observations. On DB error, returns empty context with logged warning.
    """
    start_time = time.time()
    context_parts: dict[str, Any] = {
        "summary": "",
        "traits": {},
        "weak_concepts": [],
        "prerequisites": [],
        "recent_observations": [],
    }
    result_counts = {"has_summary": False, "weak_concept_count": 0, "obs_count": 0}
    
    try:
        with get_conn() as conn:
            _load_summary(conn, user_id, subject_id, context_parts, result_counts)
            _load_traits(conn, user_id, subject_id, context_parts)
            _load_weak_concepts(conn, user_id, subject_id, context_parts, result_counts)
            _load_prerequisites(conn, user_id, subject_id, context_parts)
            _load_recent_observations(conn, user_id, subject_id, context_parts, result_counts)
            _log_retrieval_trace(conn, user_id, subject_id, result_counts)
    
    except sqlite3.Error as e:
        structured_log(
            "memory_context_error",
            user_id=user_id,
            subject_id=subject_id,
            error=str(e),
        )
        rendered = ""
    else:
        rendered = _render_memory_context(context_parts)
        latency_ms = int((time.time() - start_time) * 1000)
        structured_log(
            "memory_context_loaded",
            user_id=user_id,
            subject_id=subject_id,
            has_summary=result_counts["has_summary"],
            weak_concept_count=result_counts["weak_concept_count"],
            obs_count=result_counts["obs_count"],
            latency_ms=latency_ms,
        )
    
    return MemoryContext(
        summary=context_parts["summary"],
        traits=context_parts["traits"],
        weak_concepts=context_parts["weak_concepts"],
        prerequisites=context_parts["prerequisites"],
        recent_observations=context_parts["recent_observations"],
        rendered=rendered,
    )


def _load_summary(
    conn: sqlite3.Connection,
    user_id: int,
    subject_id: int,
    context_parts: dict[str, Any],
    result_counts: dict[str, Any],
) -> None:
    """Load current summary."""
    row = conn.execute(
        "SELECT summary FROM memory_summary WHERE user_id = ? AND subject_id = ? LIMIT 1",
        (user_id, subject_id),
    ).fetchone()
    
    if row and row["summary"]:
        context_parts["summary"] = str(row["summary"])
        result_counts["has_summary"] = True


def _load_traits(
    conn: sqlite3.Connection,
    user_id: int,
    subject_id: int,
    context_parts: dict[str, Any],
) -> None:
    """Load learner traits JSON."""
    row = conn.execute(
        "SELECT traits_json FROM learner_traits WHERE user_id = ? AND subject_id = ? LIMIT 1",
        (user_id, subject_id),
    ).fetchone()
    
    if row and row["traits_json"]:
        try:
            context_parts["traits"] = json.loads(row["traits_json"])
        except (json.JSONDecodeError, TypeError):
            context_parts["traits"] = {}


def _load_weak_concepts(
    conn: sqlite3.Connection,
    user_id: int,
    subject_id: int,
    context_parts: dict[str, Any],
    result_counts: dict[str, Any],
) -> None:
    """Load weak concepts (mastery < threshold)."""
    rows = conn.execute(
        """
        SELECT c.display_name, lcs.mastery
        FROM learner_concept_state lcs
        JOIN concepts c ON lcs.concept_id = c.id
        WHERE lcs.user_id = ? AND lcs.subject_id = ? AND lcs.mastery < ?
        ORDER BY lcs.mastery ASC
        LIMIT ?
        """,
        (user_id, subject_id, MEMORY_WEAK_MASTERY_THRESHOLD, MEMORY_WEAK_CONCEPTS_LIMIT),
    ).fetchall()
    
    weak_concepts = [
        (str(row["display_name"]), float(row["mastery"]))
        for row in rows
    ]
    context_parts["weak_concepts"] = weak_concepts
    result_counts["weak_concept_count"] = len(weak_concepts)


def _load_prerequisites(
    conn: sqlite3.Connection,
    user_id: int,
    subject_id: int,
    context_parts: dict[str, Any],
) -> None:
    """Load prerequisite edges for weak concepts."""
    if not context_parts["weak_concepts"]:
        return
    
    weak_concept_names = [name for name, _ in context_parts["weak_concepts"]]
    
    # Map concept names to IDs
    concept_ids_rows = conn.execute(
        f"""
        SELECT id, display_name FROM concepts
        WHERE subject_id = ? AND display_name IN ({','.join('?' * len(weak_concept_names))})
        """,
        [subject_id] + weak_concept_names,
    ).fetchall()
    
    concept_id_map = {row["display_name"]: row["id"] for row in concept_ids_rows}
    
    # Fetch edges where weak concepts are the "to" concept (prerequisites point to them)
    prerequisites = []
    for weak_name in weak_concept_names:
        to_id = concept_id_map.get(weak_name)
        if not to_id:
            continue
        
        edges = conn.execute(
            """
            SELECT cf.display_name as from_name, ct.display_name as to_name
            FROM concept_edges ce
            JOIN concepts cf ON ce.from_concept_id = cf.id
            JOIN concepts ct ON ce.to_concept_id = ct.id
            WHERE ce.to_concept_id = ? AND ce.relation = 'prerequisite'
            """,
            (to_id,),
        ).fetchall()
        
        for edge in edges:
            prerequisites.append((str(edge["from_name"]), str(edge["to_name"])))
    
    context_parts["prerequisites"] = prerequisites


def _load_recent_observations(
    conn: sqlite3.Connection,
    user_id: int,
    subject_id: int,
    context_parts: dict[str, Any],
    result_counts: dict[str, Any],
) -> None:
    """Load recent observations (most recent N)."""
    rows = conn.execute(
        """
        SELECT observation
        FROM learner_observations
        WHERE user_id = ? AND subject_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (user_id, subject_id, MEMORY_RECENT_OBS_LIMIT),
    ).fetchall()
    
    observations = [
        str(row["observation"]).strip()
        for row in rows
        if row["observation"]
    ]
    context_parts["recent_observations"] = observations
    result_counts["obs_count"] = len(observations)


def _log_retrieval_trace(
    conn: sqlite3.Connection,
    user_id: int,
    subject_id: int,
    result_counts: dict[str, Any],
) -> None:
    """Log retrieval to retrieval_traces (fire-and-forget)."""
    try:
        conn.execute(
            """
            INSERT INTO retrieval_traces (
                user_id, subject_id, query_text, result_json, created_at
            ) VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (
                user_id,
                subject_id,
                f"memory_context user_id={user_id} subject_id={subject_id}",
                json.dumps(result_counts),
            ),
        )
    except sqlite3.Error:
        # Silently fail; don't corrupt the read
        structured_log("memory_trace_insert_error", user_id=user_id, subject_id=subject_id)


def _render_memory_context(context_parts: dict[str, Any]) -> str:
    """Format context parts into a single rendered string for prompt injection."""
    sections = []
    
    if context_parts["summary"]:
        sections.append(f"Current summary:\n{context_parts['summary']}")
    
    if context_parts["traits"]:
        traits_items = [f"- {k}: {v}" for k, v in context_parts["traits"].items()]
        sections.append(f"Learner traits:\n" + "\n".join(traits_items))
    
    if context_parts["weak_concepts"]:
        weak_items = [
            f"- {name} (mastery: {mastery:.2f})"
            for name, mastery in context_parts["weak_concepts"]
        ]
        sections.append(f"Weak concepts:\n" + "\n".join(weak_items))
    
    if context_parts["prerequisites"]:
        prereq_items = [f"- {from_name} → {to_name}" for from_name, to_name in context_parts["prerequisites"]]
        sections.append(f"Prerequisites to reinforce:\n" + "\n".join(prereq_items))
    
    if context_parts["recent_observations"]:
        obs_items = [f"- {obs}" for obs in context_parts["recent_observations"]]
        sections.append(f"Recent learner observations:\n" + "\n".join(obs_items))
    
    return "\n\n".join(sections)


# ============================================================================
# Memory Update Queueing (with skip heuristics)
# ============================================================================


def enqueue_memory_update(
    *,
    user_id: int | None,
    subject_id: int | None,
    chat_id: int | None,
    payload: dict,
) -> EnqueueDecision:
    """Decide whether to enqueue a memory update job.
    
    Applies skip heuristics in order (free checks first, DB queries last):
      1. Missing scope
      2. No user content
      3. Turn too short
      4. Dedup (recent pending job in scope)
      5. Rate limit (too many jobs in past hour)
      6. Enqueue
    
    Returns EnqueueDecision with status, optional job_id, and reason.
    All decisions are logged for observability.
    """
    # Free checks (in-memory)
    if user_id is None or subject_id is None:
        return _make_skip_decision(user_id, subject_id, "skipped_missing_scope")
    
    user_text = _extract_user_text(payload)
    if not user_text:
        return _make_skip_decision(user_id, subject_id, "skipped_no_user_content")
    
    if len(user_text) < MEMORY_MIN_TURN_CHARS:
        return _make_skip_decision(user_id, subject_id, "skipped_short_turn")
    
    # DB checks (queries, then insert)
    try:
        with get_conn() as conn:
            # Check dedup
            if _has_pending_job(conn, user_id, subject_id):
                return _make_skip_decision(user_id, subject_id, "skipped_dedup")
            
            # Check rate limit
            if _exceeds_rate_limit(conn, user_id, subject_id):
                return _make_skip_decision(user_id, subject_id, "skipped_rate_limit")
            
            # Enqueue
            return _do_enqueue_job(conn, user_id, subject_id, chat_id, payload)
    
    except sqlite3.Error as e:
        return _make_error_decision(user_id, subject_id, str(e))
    except Exception as e:
        return _make_error_decision(user_id, subject_id, str(e))
    
    # Defensive fallback (should never reach here)
    return EnqueueDecision(enqueued=False, job_id=None, reason="db_error")


def _make_skip_decision(user_id: int | None, subject_id: int | None, reason: str) -> EnqueueDecision:
    """Create and log a skip decision."""
    decision = EnqueueDecision(enqueued=False, job_id=None, reason=reason)
    structured_log(
        "memory_enqueue_decision",
        user_id=user_id,
        subject_id=subject_id,
        enqueued=decision.enqueued,
        reason=decision.reason,
    )
    return decision


def _make_error_decision(user_id: int | None, subject_id: int | None, error: str) -> EnqueueDecision:
    """Create and log an error decision."""
    decision = EnqueueDecision(enqueued=False, job_id=None, reason="db_error")
    structured_log(
        "memory_enqueue_decision",
        user_id=user_id,
        subject_id=subject_id,
        enqueued=decision.enqueued,
        reason=decision.reason,
        error=error,
    )
    return decision


def _has_pending_job(conn: sqlite3.Connection, user_id: int, subject_id: int) -> bool:
    """Check if there's a pending/running job in the dedup window."""
    dedup_window = f"-{MEMORY_DEDUP_WINDOW_SECONDS} seconds"
    row = conn.execute(
        """
        SELECT 1 FROM memory_update_jobs
        WHERE user_id = ? AND subject_id = ?
          AND status IN ('pending', 'running')
          AND created_at > datetime('now', ?)
        LIMIT 1
        """,
        (user_id, subject_id, dedup_window),
    ).fetchone()
    return row is not None


def _exceeds_rate_limit(conn: sqlite3.Connection, user_id: int, subject_id: int) -> bool:
    """Check if the job count for this scope exceeds the hourly limit."""
    row = conn.execute(
        """
        SELECT COUNT(*) FROM memory_update_jobs
        WHERE user_id = ? AND subject_id = ? AND created_at > datetime('now', '-1 hour')
        """,
        (user_id, subject_id),
    ).fetchone()
    count = row[0] if row else 0
    return count >= MEMORY_MAX_JOBS_PER_HOUR


def _do_enqueue_job(
    conn: sqlite3.Connection,
    user_id: int,
    subject_id: int,
    chat_id: int | None,
    payload: dict,
) -> EnqueueDecision:
    """Insert the job and return enqueue decision."""
    cur = conn.execute(
        """
        INSERT INTO memory_update_jobs (
            user_id, subject_id, chat_id, status, payload_json, created_at, updated_at
        ) VALUES (?, ?, ?, 'pending', ?, datetime('now'), datetime('now'))
        """,
        (user_id, subject_id, chat_id, json.dumps(payload)),
    )
    
    job_id = cur.lastrowid
    if job_id is None:
        return _make_error_decision(user_id, subject_id, "Failed to insert job")
    
    decision = EnqueueDecision(enqueued=True, job_id=int(job_id), reason="enqueued")
    structured_log(
        "memory_enqueue_decision",
        user_id=user_id,
        subject_id=subject_id,
        enqueued=decision.enqueued,
        reason=decision.reason,
        job_id=job_id,
    )
    return decision


def _extract_user_text(payload: dict) -> str:
    """Extract user-provided text from payload.
    
    Looks for 'messages' list, filters to user role, joins non-empty strings.
    """
    if not isinstance(payload, dict):
        return ""
    
    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        return ""
    
    user_messages = [
        msg.get("content", "")
        for msg in messages
        if isinstance(msg, dict) and msg.get("role") == "user"
    ]
    
    text_parts = [str(msg).strip() for msg in user_messages if msg]
    return " ".join(text_parts)

