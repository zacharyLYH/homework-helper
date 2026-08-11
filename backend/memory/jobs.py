"""Memory job orchestration — LLM-evaluated worker.

The worker claims pending jobs from ``memory_update_jobs``, calls the LLM to
evaluate the turn, then atomically writes concept/state/trait/summary updates.
Jobs are marked ``done`` or ``failed``; the worker never raises to callers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from dataclasses import dataclass

from app.logging import get_logger
from app.structured_log import structured_log
from memory.config import (
    MEMORY_LLM_MAX_CONCEPTS,
    MEMORY_LLM_MAX_OBSERVATIONS,
    MEMORY_LLM_MAX_SUMMARY_CHARS,
    MEMORY_WEAK_CONCEPTS_LIMIT,
    MEMORY_WEAK_MASTERY_THRESHOLD,
)
from memory.db import get_conn
from memory.db import init_db
from memory.llm import evaluate_memory
from memory.schemas import (
    MemoryEvaluation,
    MemoryEvaluationInput,
)

log = get_logger(__name__)


@dataclass(frozen=True)
class WorkerBatchResult:
    claimed: int
    done: int
    failed: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_concept_key(raw: str) -> str:
    lowered = raw.strip().lower()
    replaced = re.sub(r"[^a-z0-9]+", "_", lowered)
    return replaced.strip("_")


def _parse_payload(payload_json: str | None) -> dict:
    if not payload_json:
        return {}
    parsed = json.loads(str(payload_json))
    if isinstance(parsed, dict):
        return parsed
    return {}


def _load_current_state(user_id: int, subject_id: int, payload: dict) -> MemoryEvaluationInput:
    """Read current memory state from DB and combine with payload messages."""
    messages: list[dict] = [
        {"role": str(m.get("role", "")), "content": str(m.get("content", ""))}
        for m in payload.get("messages", [])
        if isinstance(m, dict)
    ]

    current_summary = ""
    current_traits: dict[str, str] = {}
    current_weak_concepts: list[tuple[str, float]] = []

    with get_conn() as conn:
        summary_row = conn.execute(
            "SELECT summary FROM memory_summary WHERE user_id = ? AND subject_id = ?",
            (user_id, subject_id),
        ).fetchone()
        current_summary = str(summary_row["summary"]) if summary_row else ""

        traits_row = conn.execute(
            "SELECT traits_json FROM learner_traits WHERE user_id = ? AND subject_id = ?",
            (user_id, subject_id),
        ).fetchone()
        current_traits: dict[str, str] = {}
        if traits_row:
            try:
                parsed = json.loads(str(traits_row["traits_json"]))
                if isinstance(parsed, dict):
                    current_traits = {str(k): str(v) for k, v in parsed.items()}
            except json.JSONDecodeError:
                pass

        weak_rows = conn.execute(
            """
            SELECT c.display_name, lcs.mastery
            FROM learner_concept_state lcs
            JOIN concepts c ON c.id = lcs.concept_id
            WHERE lcs.user_id = ? AND lcs.subject_id = ? AND lcs.mastery < ?
            ORDER BY lcs.mastery ASC
            LIMIT ?
            """,
            (user_id, subject_id, MEMORY_WEAK_MASTERY_THRESHOLD, MEMORY_WEAK_CONCEPTS_LIMIT),
        ).fetchall()
        current_weak_concepts = [(str(r["display_name"]), float(r["mastery"])) for r in weak_rows]

    return MemoryEvaluationInput(
        user_id=user_id,
        subject_id=subject_id,
        turn_snippet=messages,
        current_summary=current_summary,
        current_traits=current_traits,
        current_weak_concepts=current_weak_concepts,
    )


def _validate_semantic(evaluation: MemoryEvaluation, *, job_id: int) -> MemoryEvaluation:
    """Apply bounded caps; returns a new MemoryEvaluation with truncations applied."""
    obs = evaluation.observations
    if len(obs) > MEMORY_LLM_MAX_OBSERVATIONS:
        structured_log(
            "memory_worker_validation_truncated",
            job_id=job_id,
            field="observations",
            original_count=len(obs),
            truncated_to=MEMORY_LLM_MAX_OBSERVATIONS,
        )
        obs = obs[:MEMORY_LLM_MAX_OBSERVATIONS]

    upserts = evaluation.concept_upserts
    if len(upserts) > MEMORY_LLM_MAX_CONCEPTS:
        structured_log(
            "memory_worker_validation_truncated",
            job_id=job_id,
            field="concept_upserts",
            original_count=len(upserts),
            truncated_to=MEMORY_LLM_MAX_CONCEPTS,
        )
        upserts = upserts[:MEMORY_LLM_MAX_CONCEPTS]

    edges = evaluation.concept_edges
    if len(edges) > MEMORY_LLM_MAX_CONCEPTS:
        structured_log(
            "memory_worker_validation_truncated",
            job_id=job_id,
            field="concept_edges",
            original_count=len(edges),
            truncated_to=MEMORY_LLM_MAX_CONCEPTS,
        )
        edges = edges[:MEMORY_LLM_MAX_CONCEPTS]

    summary = evaluation.updated_summary
    if len(summary) > MEMORY_LLM_MAX_SUMMARY_CHARS:
        structured_log(
            "memory_worker_validation_truncated",
            job_id=job_id,
            field="updated_summary",
            original_count=len(summary),
            truncated_to=MEMORY_LLM_MAX_SUMMARY_CHARS,
        )
        summary = summary[:MEMORY_LLM_MAX_SUMMARY_CHARS]

    return MemoryEvaluation(
        skip=evaluation.skip,
        observations=obs,
        concept_upserts=upserts,
        concept_edges=edges,
        concept_state_deltas=evaluation.concept_state_deltas,
        trait_updates=evaluation.trait_updates,
        updated_summary=summary,
    )


def _apply_evaluation(
    *,
    user_id: int,
    subject_id: int,
    evaluation: MemoryEvaluation,
    job_id: int,
) -> None:
    """Write all LLM-derived updates atomically in a single transaction."""
    structured_log("memory_worker_apply_start", job_id=job_id)
    tables_written: list[str] = []

    with get_conn() as conn:
        # Step 1 — concept upserts; build key→id map
        key_to_id: dict[str, int] = {}
        for cu in evaluation.concept_upserts:
            nkey = normalize_concept_key(cu.concept_key)
            if not nkey:
                log.warning("memory_worker: empty normalized key for %r, skipping", cu.concept_key)
                structured_log(
                    "memory_worker_key_normalized",
                    job_id=job_id,
                    raw_key=cu.concept_key,
                    normalized_key="(dropped)",
                )
                continue
            if nkey != cu.concept_key:
                structured_log(
                    "memory_worker_key_normalized",
                    job_id=job_id,
                    raw_key=cu.concept_key,
                    normalized_key=nkey,
                )
            aliases_json = json.dumps(cu.aliases, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO concepts (subject_id, concept_key, display_name, aliases)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(subject_id, concept_key) DO UPDATE SET
                  display_name = excluded.display_name,
                  aliases = excluded.aliases
                """,
                (subject_id, nkey, cu.display_name, aliases_json),
            )
            row = conn.execute(
                "SELECT id FROM concepts WHERE subject_id = ? AND concept_key = ?",
                (subject_id, nkey),
            ).fetchone()
            if row:
                key_to_id[nkey] = int(row["id"])
        if evaluation.concept_upserts:
            tables_written.append("concepts")

        # Step 2 — edges
        for edge in evaluation.concept_edges:
            from_nkey = normalize_concept_key(edge.from_concept_key)
            to_nkey = normalize_concept_key(edge.to_concept_key)
            for nkey in (from_nkey, to_nkey):
                if nkey not in key_to_id:
                    row = conn.execute(
                        "SELECT id FROM concepts WHERE subject_id = ? AND concept_key = ?",
                        (subject_id, nkey),
                    ).fetchone()
                    if row:
                        key_to_id[nkey] = int(row["id"])
            from_id = key_to_id.get(from_nkey)
            to_id = key_to_id.get(to_nkey)
            if from_id is None or to_id is None:
                log.warning(
                    "memory_worker: edge references unknown concept(s) %r→%r, skipping",
                    from_nkey,
                    to_nkey,
                )
                continue
            conn.execute(
                """
                INSERT INTO concept_edges (from_concept_id, to_concept_id, relation, weight)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(from_concept_id, to_concept_id, relation) DO UPDATE SET
                  weight = excluded.weight
                """,
                (from_id, to_id, edge.relation, edge.weight),
            )
        if evaluation.concept_edges:
            tables_written.append("concept_edges")

        # Step 3 — observations
        for obs in evaluation.observations:
            conn.execute(
                """
                INSERT INTO learner_observations (user_id, subject_id, observation, source)
                VALUES (?, ?, ?, 'memory_worker')
                """,
                (user_id, subject_id, obs),
            )
        if evaluation.observations:
            tables_written.append("learner_observations")

        # Step 4 — concept state
        for delta in evaluation.concept_state_deltas:
            nkey = normalize_concept_key(delta.concept_key)
            concept_id = key_to_id.get(nkey)
            if concept_id is None:
                # concept exists from a prior job but wasn't re-upserted this turn
                row = conn.execute(
                    "SELECT id FROM concepts WHERE subject_id = ? AND concept_key = ?",
                    (subject_id, nkey),
                ).fetchone()
                if row:
                    concept_id = int(row["id"])
                    key_to_id[nkey] = concept_id
            if concept_id is None:
                log.warning("memory_worker: state delta for unknown concept %r, skipping", nkey)
                continue
            conn.execute(
                """
                INSERT INTO learner_concept_state (user_id, subject_id, concept_id, mastery, confidence)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, subject_id, concept_id) DO UPDATE SET
                  mastery = excluded.mastery,
                  confidence = excluded.confidence,
                  updated_at = datetime('now')
                """,
                (user_id, subject_id, concept_id, delta.mastery, delta.confidence),
            )
        if evaluation.concept_state_deltas:
            tables_written.append("learner_concept_state")

        # Step 5 — traits merge
        if evaluation.trait_updates:
            traits_row = conn.execute(
                "SELECT traits_json FROM learner_traits WHERE user_id = ? AND subject_id = ?",
                (user_id, subject_id),
            ).fetchone()
            existing: dict[str, str] = {}
            if traits_row:
                try:
                    parsed = json.loads(str(traits_row["traits_json"]))
                    if isinstance(parsed, dict):
                        existing = {str(k): str(v) for k, v in parsed.items()}
                except json.JSONDecodeError:
                    pass
            merged = {**existing, **evaluation.trait_updates}
            conn.execute(
                """
                INSERT INTO learner_traits (user_id, subject_id, traits_json)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, subject_id) DO UPDATE SET
                  traits_json = excluded.traits_json,
                  updated_at = datetime('now')
                """,
                (user_id, subject_id, json.dumps(merged, ensure_ascii=False)),
            )
            tables_written.append("learner_traits")

        # Step 6 — summary
        if evaluation.updated_summary:
            conn.execute(
                """
                INSERT INTO memory_summary (user_id, subject_id, summary)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, subject_id) DO UPDATE SET
                  summary = excluded.summary,
                  updated_at = datetime('now')
                """,
                (user_id, subject_id, evaluation.updated_summary),
            )
            tables_written.append("memory_summary")

    structured_log(
        "memory_worker_apply_done",
        job_id=job_id,
        tables_written=tables_written,
    )


# ---------------------------------------------------------------------------
# Job claim / status helpers
# ---------------------------------------------------------------------------


def _claim_next_pending_job() -> dict | None:
    row_data: dict | None = None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, subject_id, chat_id, payload_json
            FROM memory_update_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """
        ).fetchone()

        if row is None:
            return None

        cur = conn.execute(
            """
            UPDATE memory_update_jobs
            SET status = 'running', updated_at = datetime('now')
            WHERE id = ? AND status = 'pending'
            """,
            (row["id"],),
        )
        if cur.rowcount != 1:
            return None

        row_data = {
            "id": int(row["id"]),
            "user_id": int(row["user_id"]),
            "subject_id": int(row["subject_id"]),
            "chat_id": row["chat_id"],
            "payload_json": row["payload_json"],
        }

    return row_data


def _set_job_done(job_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE memory_update_jobs
            SET status = 'done', updated_at = datetime('now')
            WHERE id = ?
            """,
            (job_id,),
        )


def _set_job_failed(job_id: int, *, payload_json: str | None, error: str) -> None:
    next_payload: dict = {"worker_error": error[:400]}
    if payload_json:
        try:
            parsed = json.loads(payload_json)
            if isinstance(parsed, dict):
                next_payload = {**parsed, "worker_error": error[:400]}
        except json.JSONDecodeError:
            next_payload["raw_payload_json"] = payload_json[:1000]

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE memory_update_jobs
            SET status = 'failed', payload_json = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (json.dumps(next_payload), job_id),
        )


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------


def _process_claimed_job(job: dict, loop: asyncio.AbstractEventLoop) -> bool:
    """Process one claimed job. Returns True on success, False on failure.

    Never raises — all errors are caught and the job is marked ``failed``.
    """
    job_id = int(job["id"])
    user_id = int(job["user_id"])
    subject_id = int(job["subject_id"])

    t0 = time.monotonic()
    structured_log("memory_worker_llm_start", job_id=job_id, user_id=user_id, subject_id=subject_id)

    try:
        payload = _parse_payload(job.get("payload_json"))
        current_state = _load_current_state(user_id, subject_id, payload)

        evaluation = loop.run_until_complete(evaluate_memory(current_state=current_state))
        evaluation = _validate_semantic(evaluation, job_id=job_id)

        latency_ms = int((time.monotonic() - t0) * 1000)
        structured_log(
            "memory_worker_llm_done",
            job_id=job_id,
            latency_ms=latency_ms,
            skip=evaluation.skip,
            observations_count=len(evaluation.observations),
            concepts_count=len(evaluation.concept_upserts),
        )

        if evaluation.skip:
            return True

        _apply_evaluation(
            user_id=user_id,
            subject_id=subject_id,
            evaluation=evaluation,
            job_id=job_id,
        )
        return True

    except Exception as exc:
        # asyncio.TimeoutError str() is empty in Python 3.10; use repr() for clarity
        error_msg = repr(exc) if not str(exc) else str(exc)
        structured_log("memory_worker_llm_error", job_id=job_id, error=error_msg[:400])
        log.warning("Memory worker failed job_id=%s error=%s", job_id, error_msg)
        _set_job_failed(job_id, payload_json=job.get("payload_json"), error=error_msg)
        return False


def process_pending_jobs(
    *,
    batch_size: int = 20,
    loop: asyncio.AbstractEventLoop | None = None,
) -> WorkerBatchResult:
    _loop = loop if loop is not None else asyncio.new_event_loop()
    close_loop = loop is None

    claimed = 0
    done = 0
    failed = 0

    try:
        for _ in range(max(1, batch_size)):
            job = _claim_next_pending_job()
            if job is None:
                break

            claimed += 1
            job_id = int(job["id"])

            try:
                success = _process_claimed_job(job, _loop)
            except Exception as exc:  # pragma: no cover - defensive guard
                log.error("Unexpected error in worker job_id=%s: %s", job_id, exc)
                _set_job_failed(job_id, payload_json=job.get("payload_json"), error=str(exc))
                failed += 1
                continue

            if success:
                done += 1
                _set_job_done(job_id)
                log.info("Memory worker completed job_id=%s", job_id)
            else:
                failed += 1
    finally:
        if close_loop:
            _loop.close()

    return WorkerBatchResult(claimed=claimed, done=done, failed=failed)


def run_worker_loop(
    *,
    poll_interval_s: float,
    batch_size: int,
    loop: asyncio.AbstractEventLoop,
) -> None:
    log.info(
        "Memory worker started: poll_interval_s=%s batch_size=%s",
        poll_interval_s,
        batch_size,
    )
    while True:
        result = process_pending_jobs(batch_size=batch_size, loop=loop)
        if result.claimed == 0:
            time.sleep(max(0.1, poll_interval_s))


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run memory update worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one batch and exit",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds to wait when no pending jobs are available",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Maximum jobs to process per batch",
    )
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    db_path = init_db()
    log.info(f"Memory worker schema ready: {db_path}")

    loop = asyncio.new_event_loop()
    try:
        if args.once:
            result = process_pending_jobs(
                batch_size=max(1, int(args.batch_size)),
                loop=loop,
            )
            log.info(
                "Memory worker one-shot finished: claimed=%s done=%s failed=%s",
                result.claimed,
                result.done,
                result.failed,
            )
            return 0

        run_worker_loop(
            poll_interval_s=max(0.1, float(args.poll_interval)),
            batch_size=max(1, int(args.batch_size)),
            loop=loop,
        )
    finally:
        loop.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
