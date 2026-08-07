"""Memory job orchestration entrypoints.

The worker is intentionally deterministic and best-effort:
- it claims pending jobs from ``memory_update_jobs``
- extracts a compact learner observation from payload JSON
- appends observations and creates a new memory summary version
- marks jobs ``done`` or ``failed`` without raising to callers
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass

from app.logging import get_logger
from memory.db import get_conn
from memory.db import init_db

log = get_logger(__name__)


@dataclass(frozen=True)
class WorkerBatchResult:
    claimed: int
    done: int
    failed: int


def _extract_observation(payload: dict) -> str:
	messages = payload.get("messages")
	if isinstance(messages, list):
		for msg in reversed(messages):
			if not isinstance(msg, dict):
				continue
			role = str(msg.get("role", "")).strip().lower()
			content = str(msg.get("content", "")).strip()
			if role == "user" and content:
				return f"Learner said: {content[:280]}"

		for msg in reversed(messages):
			if not isinstance(msg, dict):
				continue
			role = str(msg.get("role", "")).strip().lower()
			content = str(msg.get("content", "")).strip()
			if role == "assistant" and content:
				return f"Assistant feedback: {content[:280]}"

	trigger = str(payload.get("trigger", "chat_turn")).strip() or "chat_turn"
	return f"Memory update captured from {trigger}."


def _build_summary(*, user_id: int, subject_id: int) -> str:
	rows = []
	with get_conn() as conn:
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

	observations = [str(row["observation"]).strip() for row in rows if row["observation"]]
	if not observations:
		return "Recent learner observations:\n- No observations available yet."

	bullets = "\n".join(f"- {item}" for item in observations)
	return f"Recent learner observations:\n{bullets}"


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
    next_payload = {"worker_error": error[:400]}
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


def _create_memory_version(*, user_id: int, subject_id: int, summary: str) -> int:
	version_id_int = 0
	with get_conn() as conn:
		version_row = conn.execute(
			"""
			SELECT COALESCE(MAX(version), 0) + 1 AS next_version
			FROM memory_versions
			WHERE user_id = ? AND subject_id = ?
			""",
			(user_id, subject_id),
		).fetchone()
		next_version = int(version_row["next_version"]) if version_row else 1

		cur = conn.execute(
			"""
			INSERT INTO memory_versions (user_id, subject_id, version, summary)
			VALUES (?, ?, ?, ?)
			""",
			(user_id, subject_id, next_version, summary),
		)
		version_id = cur.lastrowid
		if version_id is None:
			raise RuntimeError("Failed to create memory version")
		version_id_int = int(version_id)

		existing = conn.execute(
			"""
			SELECT id FROM memory_current
			WHERE user_id = ? AND subject_id = ?
			LIMIT 1
			""",
			(user_id, subject_id),
		).fetchone()

		if existing is None:
			conn.execute(
				"""
				INSERT INTO memory_current (user_id, subject_id, version_id, updated_at)
				VALUES (?, ?, ?, datetime('now'))
				""",
				(user_id, subject_id, version_id_int),
			)
		else:
			conn.execute(
				"""
				UPDATE memory_current
				SET version_id = ?, updated_at = datetime('now')
				WHERE id = ?
				""",
				(version_id_int, int(existing["id"])),
			)

	return version_id_int


def _process_claimed_job(job: dict) -> None:
    payload_raw = job.get("payload_json")
    payload: dict = {}
    if payload_raw:
        parsed = json.loads(str(payload_raw))
        if isinstance(parsed, dict):
            payload = parsed

    observation = _extract_observation(payload)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO learner_observations (user_id, subject_id, observation, source)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(job["user_id"]),
                int(job["subject_id"]),
                observation,
                "memory_worker",
            ),
        )

    summary = _build_summary(
        user_id=int(job["user_id"]),
        subject_id=int(job["subject_id"]),
    )
    _create_memory_version(
        user_id=int(job["user_id"]),
        subject_id=int(job["subject_id"]),
        summary=summary,
    )


def process_pending_jobs(*, batch_size: int = 20) -> WorkerBatchResult:
    claimed = 0
    done = 0
    failed = 0

    for _ in range(max(1, batch_size)):
        job = _claim_next_pending_job()
        if job is None:
            break

        claimed += 1
        job_id = int(job["id"])
        try:
            _process_claimed_job(job)
        except Exception as exc:  # pragma: no cover - defensive guard
            failed += 1
            _set_job_failed(job_id, payload_json=job.get("payload_json"), error=str(exc))
            log.warning("Memory worker failed job_id=%s error=%s", job_id, exc)
            continue

        done += 1
        _set_job_done(job_id)
        log.info("Memory worker completed job_id=%s", job_id)

    return WorkerBatchResult(claimed=claimed, done=done, failed=failed)


def run_worker_loop(*, poll_interval_s: float, batch_size: int) -> None:
    log.info(
        "Memory worker started: poll_interval_s=%s batch_size=%s",
        poll_interval_s,
        batch_size,
    )
    while True:
        result = process_pending_jobs(batch_size=batch_size)
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

    if args.once:
        result = process_pending_jobs(batch_size=max(1, int(args.batch_size)))
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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
