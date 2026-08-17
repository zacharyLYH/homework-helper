"""Memory service layer: synchronous skip logic and context loading.

Functions:
  - get_memory_runtime_status: Check if memory DB is ready
  - enforce_memory_runtime: Raise if memory is required but unavailable
  - load_memory_context: Assemble multi-section context for agent prompt
  - enqueue_memory_update: Decide whether to enqueue a worker job (with skip heuristics)
"""

import sqlite3
import time
from typing import Any

from app.structured_log import structured_log
from memory.config import (
    MEMORY_MIN_TURN_CHARS,
    resolve_memory_db_path,
)
from memory.db import get_conn
from memory.db import missing_required_tables
from shared.schemas import EnqueueDecision
from shared.schemas import MemoryContext
from shared.schemas import MemoryRuntimeStatus
from shared.schemas import MemoryUpdatePayload
from memory.service.utils import _do_enqueue_job
from memory.service.utils import _exceeds_rate_limit
from memory.service.utils import _extract_user_text
from memory.service.utils import _has_pending_job
from memory.service.utils import _load_prerequisites
from memory.service.utils import _load_recent_observations
from memory.service.utils import _load_summary
from memory.service.utils import _load_traits
from memory.service.utils import _load_weak_concepts
from memory.service.utils import _log_retrieval_trace
from memory.service.utils import _make_error_decision
from memory.service.utils import _make_skip_decision
from memory.service.utils import _render_memory_context
from memory.structured_log_interface import get_enqueue_trace_id


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


# ============================================================================
# Memory Update Queueing (with skip heuristics)
# ============================================================================


def enqueue_memory_update(
    *,
    user_id: int | None,
    subject_id: int | None,
    chat_id: int | None,
    payload: MemoryUpdatePayload,
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
    trace_id = get_enqueue_trace_id()

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
            return _do_enqueue_job(conn, user_id, subject_id, chat_id, payload, trace_id)

    except sqlite3.Error as e:
        return _make_error_decision(user_id, subject_id, str(e))
    except Exception as e:
        return _make_error_decision(user_id, subject_id, str(e))

    # Defensive fallback (should never reach here)
    return EnqueueDecision(enqueued=False, job_id=None, reason="db_error")
