"""Memory job orchestration - LLM-evaluated worker.

The worker claims pending jobs from ``memory_update_jobs``, calls the LLM to
evaluate the turn, then atomically writes concept/state/trait/summary updates.
Jobs are marked ``done`` or ``failed``; the worker never raises to callers.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass

from app.logging import get_logger
from app.structured_log import structured_log
from memory.db import init_db
from memory.jobs.utils import _apply_evaluation
from memory.jobs.utils import _claim_next_pending_job
from memory.jobs.utils import _load_current_state
from memory.jobs.utils import _parse_payload
from memory.jobs.utils import _set_job_done
from memory.jobs.utils import _set_job_failed
from memory.jobs.utils import _validate_semantic
from memory.llm import evaluate_memory

log = get_logger(__name__)


@dataclass(frozen=True)
class WorkerBatchResult:
    claimed: int
    done: int
    failed: int


def _process_claimed_job(job: dict, loop: asyncio.AbstractEventLoop) -> bool:
    """Process one claimed job. Returns True on success, False on failure.

    Never raises - all errors are caught and the job is marked ``failed``.
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
