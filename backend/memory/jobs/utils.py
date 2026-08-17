"""Helper functions for memory worker orchestration and DB writes."""

from __future__ import annotations

import json
import re
from typing import Any

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
from memory.schemas import MemoryEvaluation
from memory.schemas import MemoryEvaluationInput
from shared.schemas import MemoryUpdatePayload

log = get_logger(__name__)


def normalize_concept_key(raw: str) -> str:
    lowered = raw.strip().lower()
    replaced = re.sub(r"[^a-z0-9]+", "_", lowered)
    return replaced.strip("_")


def _parse_payload(payload_json: str | None) -> MemoryUpdatePayload:
    """Parse a stored job payload into the typed app<->worker contract.

    Malformed/missing payloads normalize to an empty payload so downstream
    processing never sees raw JSON. Raises on unparseable JSON so the caller
    can mark the job failed.
    """
    if not payload_json:
        return MemoryUpdatePayload(
            trigger="", memory_loaded=False, memory_context="", messages=[]
        )
    parsed = json.loads(str(payload_json))
    if isinstance(parsed, dict):
        messages = [
            {"role": str(m.get("role", "")), "content": str(m.get("content", ""))}
            for m in parsed.get("messages", [])
            if isinstance(m, dict)
        ]
        return MemoryUpdatePayload(
            trigger=str(parsed.get("trigger", "")),
            memory_loaded=bool(parsed.get("memory_loaded", False)),
            memory_context=str(parsed.get("memory_context", "")),
            messages=messages,
        )
    return MemoryUpdatePayload(
        trigger="", memory_loaded=False, memory_context="", messages=[]
    )


def _load_current_state(user_id: int, subject_id: int, payload: MemoryUpdatePayload) -> MemoryEvaluationInput:
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
        # Step 1 - concept upserts; build key->id map
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

        # Step 2 - edges
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
                    "memory_worker: edge references unknown concept(s) %r->%r, skipping",
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

        # Step 3 - observations
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

        # Step 4 - concept state
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

        # Step 5 - traits merge
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

        # Step 6 - summary
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


def _claim_next_pending_job() -> dict[str, Any] | None:
    row_data: dict[str, Any] | None = None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, subject_id, chat_id, trace_id, payload_json
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
            "trace_id": row["trace_id"],
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
    next_payload: dict[str, Any] = {"worker_error": error[:400]}
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
