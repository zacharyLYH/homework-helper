"""Big edge cases for the memory pipeline, driven organically.

Same three-process shape as the other e2e tests (real backend, real worker
loop, mock LLM over HTTP). Each test exercises a failure/degenerate boundary
end to end:

  * alignment-gate rejection — no job, no memory, nothing persisted
  * short-turn skip — gate passes but the enqueue heuristic declines
  * dedup window — a second turn while a job is ``running`` is skipped
  * dedup burst — N concurrent turns in one scope: exactly one enqueues
  * worker crash — the worker dies mid-eval; the orphaned 'running' job is
    reclaimed on restart and the update is not lost
  * poison eval — the worker's LLM returns garbage; job fails, pipeline lives
  * llm timeout — the worker's LLM stalls past MEMORY_LLM_TIMEOUT_SECONDS;
    the most common real fault. Job fails, error is diagnosable (repr —
    ``str(TimeoutError)`` is empty), the worker is not wedged
  * oversized eval — bounded caps truncate, job still succeeds
  * key normalization — messy LLM concept keys land in canonical form
  * cross-user authz — memory endpoints 404 for other users' subjects

Determinism rules (same as the other tests): routes registered BEFORE the
turn that enqueues the matching job; waits are absolute (">= N terminal").
"""

from __future__ import annotations

import asyncio
import json

import httpx

from .harness import (
    Harness,
    chat_turn,
    create_chat,
    create_subject,
    memory_eval,
)

# Gate-proven homework text (verified against the real encoder: scores 0.47+,
# threshold 0.4) and a gate-rejected off-topic message (score 0.18).
_MSG_HW = "I need help with my physics homework on projectile motion"
_MSG_HW_2 = "I need help with my physics homework on kinematics equations"
_MSG_SHORT = "help me"  # passes the gate (0.62) but is < MEMORY_MIN_TURN_CHARS
_MSG_OFF_TOPIC = "what's the weather like today"  # gate-rejected (0.18)


async def _wait_any_job_running(harness: Harness) -> None:
    """Poll (async, non-blocking) until some memory job is in 'running'."""
    while "running" not in harness.job_statuses():
        await asyncio.sleep(0.05)


async def test_alignment_rejection_enqueues_nothing(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    token = harness.register_user("edge1@school.edu")
    harness.seed_llm_config(token)
    subject_id = await create_subject(e2e_client, token, "Math")
    chat_id = await create_chat(e2e_client, token, subject_id)

    reply = await chat_turn(e2e_client, token, chat_id, _MSG_OFF_TOPIC)

    # The user gets the scope-guard reply, the agent never runs.
    assert "homework questions only" in reply, reply
    # Nothing enqueued, nothing evaluated, nothing persisted.
    assert harness.wait_enqueue_reasons(0) == []
    eval_calls = [c for c in harness.mock_calls() if not c["stream"]]
    assert eval_calls == []
    msgs = harness.sql("app", "SELECT COUNT(*) AS n FROM messages")[0]["n"]
    assert msgs == 0


async def test_short_turn_skips_enqueue_but_chat_works(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    token = harness.register_user("edge2@school.edu")
    harness.seed_llm_config(token)
    subject_id = await create_subject(e2e_client, token, "Math")
    chat_id = await create_chat(e2e_client, token, subject_id)

    reply = await chat_turn(e2e_client, token, chat_id, _MSG_SHORT)

    assert reply.strip()
    assert harness.wait_enqueue_reasons(1) == ["skipped_short_turn"]
    assert harness.job_statuses() == []
    assert harness.memory_count("learner_observations") == 0


async def test_dedup_skips_turn_while_previous_job_is_running(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    token = harness.register_user("edge3@school.edu")
    harness.seed_llm_config(token)
    subject_id = await create_subject(e2e_client, token, "Math")
    chat_id = await create_chat(e2e_client, token, subject_id)

    # Route turn 1's eval with a delay so job 1 sits in 'running' long enough
    # for turn 2 to land inside the dedup window.
    harness.mock_route(
        {
            "match": "projectile motion",
            "delay_ms": 2500,
            "memory": memory_eval(
                observations=["Learner mixes up which kinematic equation to pick."],
                updated_summary="Learner starting projectile motion; picking equations is shaky.",
            ),
        }
    )

    reply1 = await chat_turn(e2e_client, token, chat_id, _MSG_HW)
    assert reply1.strip()
    reply2 = await chat_turn(e2e_client, token, chat_id, _MSG_HW_2)
    assert reply2.strip()

    # Turn 1 enqueued; turn 2 was declined by the dedup heuristic.
    assert harness.wait_enqueue_reasons(2) == ["enqueued", "skipped_dedup"]
    assert harness.wait_jobs_done(1) == ["done"]
    assert harness.memory_count("learner_observations") == 1

    # The skipped turn's eval never ran (no second eval request in the log).
    eval_calls = [c for c in harness.mock_calls() if not c["stream"]]
    assert len(eval_calls) == 1, eval_calls


async def test_concurrent_burst_in_one_scope_enqueues_exactly_one_job(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    """Race N same-scope turns against the dedup check-then-insert.

    The enqueue path reads ``_has_pending_job`` and inserts within one DB
    transaction, so under a same-scope burst the first insert wins and the
    other turns see the pending job and skip. Skipped turns still chat fine.
    """
    token = harness.register_user("edge9@school.edu")
    harness.seed_llm_config(token)
    subject_id = await create_subject(e2e_client, token, "Math")
    chat_id = await create_chat(e2e_client, token, subject_id)

    harness.mock_route(
        {
            "match": "projectile motion",
            "delay_ms": 2500,  # keep the winner 'running' during the burst
            "memory": memory_eval(updated_summary="Burst turn processed."),
        }
    )

    replies = await asyncio.gather(
        *(chat_turn(e2e_client, token, chat_id, _MSG_HW) for _ in range(5))
    )
    assert all(r.strip() for r in replies)  # memory skips never break the chat

    reasons = harness.wait_enqueue_reasons(5)
    assert reasons.count("enqueued") == 1, reasons
    assert reasons.count("skipped_dedup") == 4, reasons
    assert harness.wait_jobs_done(1) == ["done"]
    assert harness.memory_count("memory_summary") == 1


async def test_worker_crash_orphaned_job_is_reclaimed_on_restart(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    """SIGKILL the worker mid-eval; the orphaned job must not be lost.

    Without reclaim, the killed worker's 'running' job would sit forever and
    the learner's memory update would be silently dropped. The stale-reclaim
    pass (MEMORY_STALE_JOB_SECONDS=5 in the harness env) requeues it on the
    next worker start; the job is reclaimed (not re-enqueued), so dedup and
    the hourly rate limit never see it twice.
    """
    token = harness.register_user("edge10@school.edu")
    harness.seed_llm_config(token)
    subject_id = await create_subject(e2e_client, token, "Math")
    chat_id = await create_chat(e2e_client, token, subject_id)

    # Hold the eval well past the stale threshold so we can kill the worker
    # while the job is genuinely 'running' (not between batches). The eval
    # runs twice (killed attempt + reclaimed retry): times=2 + retry_delay_ms
    # serve a slow first attempt, then a fast retry that fits the 3s timeout.
    harness.mock_route(
        {
            "match": "projectile motion",
            "delay_ms": 15000,
            "retry_delay_ms": 0,
            "times": 2,
            "memory": memory_eval(
                observations=["Post-crash write proves the update survived."],
                updated_summary="Survived a worker crash.",
            ),
        }
    )
    turn_task = asyncio.create_task(chat_turn(e2e_client, token, chat_id, _MSG_HW))

    async def kill_when_eval_in_flight() -> None:
        # Kill only once attempt 1 has actually reached the mock LLM (the
        # mock logs the request before honoring delay_ms). Killing earlier
        # would let the reclaimed retry inherit attempt 1's slow delay.
        await _wait_any_job_running(harness)
        harness.wait_eval_calls(1)
        harness.restart_worker()

    await asyncio.gather(turn_task, kill_when_eval_in_flight())

    # The reclaimed job completes with the routed eval (routes live in the
    # mock process, so the spec survives the worker restart). One observation
    # — not two — proves the update was applied exactly once.
    assert harness.wait_jobs_done(1) == ["done"]
    assert harness.memory_count("learner_observations") == 1
    summary = str(
        harness.sql("memory", "SELECT summary FROM memory_summary")[0]["summary"]
    )
    assert summary == "Survived a worker crash."

    # Exactly one job row: reclaimed, not duplicated by re-enqueue.
    assert len(harness.job_statuses()) == 1


async def test_poison_eval_fails_job_without_poisoning_pipeline(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    token = harness.register_user("edge4@school.edu")
    harness.seed_llm_config(token)
    subject_id = await create_subject(e2e_client, token, "Math")
    chat_id = await create_chat(e2e_client, token, subject_id)

    # Turn 1: routed eval returns text that is not JSON at all.
    harness.mock_route({"match": "projectile motion", "memory": "not-json{{"})
    await chat_turn(e2e_client, token, chat_id, _MSG_HW)
    assert harness.wait_jobs_done(1) == ["failed"]
    assert harness.memory_count("concepts") == 0
    assert harness.memory_count("memory_summary") == 0

    # The pipeline survives: the next turn enqueues, drains, and writes memory.
    harness.mock_route(
        {
            "match": "kinematics equations",
            "memory": memory_eval(updated_summary="Learner working on kinematics."),
        }
    )
    await chat_turn(e2e_client, token, chat_id, _MSG_HW_2)
    assert harness.wait_jobs_done(2) == ["failed", "done"]
    assert harness.memory_count("memory_summary") == 1

    # The failure is diagnosable: the job row carries the worker error.
    row = harness.sql(
        "memory", "SELECT payload_json FROM memory_update_jobs WHERE status = 'failed'"
    )[0]
    assert "worker_error" in json.loads(str(row["payload_json"]))


async def test_llm_timeout_fails_job_without_wedging_worker(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    token = harness.register_user("edge7@school.edu")
    harness.seed_llm_config(token)
    subject_id = await create_subject(e2e_client, token, "Math")
    chat_id = await create_chat(e2e_client, token, subject_id)

    # The worker's eval stalls far past MEMORY_LLM_TIMEOUT_SECONDS (3s in the
    # harness env; the mock holds the response for 8s).
    harness.mock_route(
        {"match": "projectile motion", "delay_ms": 8000, "memory": memory_eval()}
    )
    await chat_turn(e2e_client, token, chat_id, _MSG_HW)
    assert harness.wait_jobs_done(1) == ["failed"]

    # No memory was written by the timed-out job.
    assert harness.memory_count("learner_observations") == 0
    assert harness.memory_count("memory_summary") == 0

    # The failure is diagnosable: str(TimeoutError) is empty, so the worker
    # persists repr() — the job row must name the fault.
    row = harness.sql(
        "memory", "SELECT payload_json FROM memory_update_jobs WHERE status = 'failed'"
    )[0]
    assert "TimeoutError" in json.loads(str(row["payload_json"]))["worker_error"]

    # The timeout did not wedge the worker: the next turn enqueues (the failed
    # job is terminal, so dedup does not apply), drains, and writes memory.
    # Its eval is unscripted → the mock's organic default (skip) marks it done.
    await chat_turn(e2e_client, token, chat_id, _MSG_HW_2)
    assert harness.wait_jobs_done(2) == ["failed", "done"]


async def test_oversized_eval_is_truncated_to_caps(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    token = harness.register_user("edge5@school.edu")
    harness.seed_llm_config(token)
    subject_id = await create_subject(e2e_client, token, "Math")
    chat_id = await create_chat(e2e_client, token, subject_id)

    # Way past every cap: 8 observations (max 5), 14 concepts/edges (max 10),
    # a 900-char summary (max 500).
    harness.mock_route(
        {
            "match": "projectile motion",
            "memory": memory_eval(
                observations=[f"Observation number {i}" for i in range(1, 9)],
                concept_upserts=[
                    {"concept_key": f"topic_{i:02d}", "display_name": f"Topic {i}", "aliases": []}
                    for i in range(1, 15)
                ],
                concept_edges=[
                    {
                        "from_concept_key": "topic_01",
                        "to_concept_key": f"topic_{i:02d}",
                        "relation": "related",
                        "weight": 0.5,
                    }
                    for i in range(2, 15)
                ],
                updated_summary="x" * 900,
            ),
        }
    )
    await chat_turn(e2e_client, token, chat_id, _MSG_HW)
    assert harness.wait_jobs_done(1) == ["done"]

    assert harness.memory_count("learner_observations") == 5  # MEMORY_LLM_MAX_OBSERVATIONS
    assert harness.memory_count("concepts") == 10  # MEMORY_LLM_MAX_CONCEPTS
    # Cap truncation cascades to edges: 10 kept, but topic_01→topic_11 lost its
    # endpoint to the concept cap, so the worker drops that edge → 9 written.
    assert harness.memory_count("concept_edges") == 9
    assert harness.memory_count("learner_concept_state") == 0  # none sent
    summary = str(
        harness.sql("memory", "SELECT summary FROM memory_summary")[0]["summary"]
    )
    assert len(summary) == 500


async def test_concept_keys_are_normalized(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    token = harness.register_user("edge6@school.edu")
    harness.seed_llm_config(token)
    subject_id = await create_subject(e2e_client, token, "Math")
    chat_id = await create_chat(e2e_client, token, subject_id)

    harness.mock_route(
        {
            "match": "projectile motion",
            "memory": memory_eval(
                concept_upserts=[
                    {
                        "concept_key": "  Kinematic Equations!  ",
                        "display_name": "Kinematic Equations",
                    },
                    {"concept_key": "…", "display_name": "Punctuation Only"},
                ],
                concept_state_deltas=[
                    {"concept_key": "KINEMATIC-equations", "mastery": 0.2, "confidence": 0.9}
                ],
                concept_edges=[
                    {
                        "from_concept_key": "Kinematic Equations!",
                        "to_concept_key": "KINEMATIC-equations",
                        "relation": "related",
                        "weight": 0.7,
                    }
                ],
                updated_summary="Messy-key turn.",
            ),
        }
    )
    await chat_turn(e2e_client, token, chat_id, _MSG_HW)
    assert harness.wait_jobs_done(1) == ["done"]

    # "  Kinematic Equations!  ", "KINEMATIC-equations" all collapse onto one
    # canonical key; "…" normalizes to empty and is dropped entirely.
    keys = [
        str(r["concept_key"])
        for r in harness.sql("memory", "SELECT concept_key FROM concepts")
    ]
    assert keys == ["kinematic_equations"], keys
    row = harness.sql("memory", "SELECT mastery FROM learner_concept_state")[0]
    assert float(row["mastery"]) == 0.2  # delta landed on the normalized concept
    assert harness.memory_count("concept_edges") == 1  # both endpoints resolved


async def test_memory_endpoints_reject_other_users(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    owner = harness.register_user("edge11@school.edu")
    harness.seed_llm_config(owner)
    subject_id = await create_subject(e2e_client, owner, "Math")
    outsider = harness.register_user("edge12@school.edu")

    for path in (
        f"/api/memory/subjects/{subject_id}/context",
        f"/api/memory/subjects/{subject_id}/jobs",
    ):
        r = await e2e_client.get(path, headers=Harness.auth(outsider))
        assert r.status_code == 404, (path, r.status_code)
        assert r.json()["detail"] == "Subject not found"
