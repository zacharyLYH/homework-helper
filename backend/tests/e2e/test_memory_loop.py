"""Organic multi-loop memory test against a real HTTP backend.

Everything here is driven over genuine HTTP: a real backend server process, a
real memory worker polling as its own process (production shape), and a real
mock-LLM server the backend's provider clients call over HTTP. The only thing
"faked" is the LLM content itself, served by the local mock.

Tests never crank the worker: they chat, script what the worker's LLM should
return per turn (content-routed on the turn text), and wait for the job queue
to drain. The worker's organic default for unscripted evals is a skip.

Two rules keep this deterministic against a live worker:
  * eval routes are registered BEFORE the turn that enqueues the matching job
    (the worker may claim a job the instant it appears)
  * waits are absolute (">= N jobs terminal"), never delta-based

Flow under test:
  * start state has no memory and no jobs
  * chats kick off memory jobs
  * some jobs turn into durable memory (concepts / observations / summary)
  * other jobs are evaluated as "skip" and change nothing (not every job -> memory)
  * accumulated memory is loaded into the prompts of later chats
"""

from __future__ import annotations

import httpx

from .harness import Harness, chat_turn, create_chat, create_subject, memory_eval, skip_eval

_TURN1 = "For my algebra homework, I keep making sign mistakes in the quadratic formula"
_TURN2 = "How should I avoid making that sign mistake on my algebra homework?"
_TURN3 = "Can you give me another practice problem that needs the quadratic formula?"


async def test_memory_loop_organic(harness: Harness, e2e_client: httpx.AsyncClient) -> None:
    # --- Start state: no memory, no jobs ---
    assert harness.memory_count("concepts") == 0
    assert harness.memory_count("learner_observations") == 0
    assert harness.memory_count("memory_summary") == 0
    assert harness.job_statuses() == []

    token = harness.register_user("sandy@school.edu")
    harness.seed_llm_config(token)
    subject_id = await create_subject(e2e_client, token, "Math")
    chat_id = await create_chat(e2e_client, token, subject_id)

    # Route turn 1's eval BEFORE the turn (the worker may claim instantly).
    harness.mock_route(
        {
            "match": "sign mistakes in the quadratic formula",
            "memory": memory_eval(
                observations=["Learner confuses the signs in the quadratic formula"],
                concept_upserts=[
                    {
                        "concept_key": "quadratic_formula",
                        "display_name": "Quadratic Formula",
                        "aliases": [],
                    }
                ],
                concept_state_deltas=[
                    {"concept_key": "quadratic_formula", "mastery": 0.3, "confidence": 0.9}
                ],
                trait_updates={"pace": "careful"},
                updated_summary="Learner needs practice tracking signs in the quadratic formula.",
            ),
        }
    )

    # --- Turn 1: a chat with no memory yet kicks off a job, prompt has no memory ---
    reply1 = await chat_turn(e2e_client, token, chat_id, _TURN1)
    assert reply1.strip()
    turn1_call = harness.chat_calls()[-1]
    assert "LEARNER MEMORY CONTEXT" not in turn1_call["text"]

    # Background worker: job 1 is evaluated (scripted by content) → durable memory.
    assert harness.wait_jobs_done(1) == ["done"]
    assert harness.memory_count("concepts") == 1
    assert harness.memory_count("learner_observations") == 1
    assert harness.memory_count("memory_summary") == 1

    # --- Turn 2: memory from job 1 is loaded into the prompt; kicks off job 2 ---
    reply2 = await chat_turn(e2e_client, token, chat_id, _TURN2)
    assert reply2.strip()
    turn2_call = harness.chat_calls()[-1]
    assert "LEARNER MEMORY CONTEXT" in turn2_call["text"]
    # Exact ground truth: summary, observation, trait, and weak-concept mastery
    # all reached the real model over the wire.
    assert "Learner needs practice tracking signs" in turn2_call["text"]
    assert "Learner confuses the signs" in turn2_call["text"]
    assert "pace: careful" in turn2_call["text"]
    assert "Quadratic Formula (mastery: 0.30)" in turn2_call["text"]

    # Background worker: job 2 is a skip → done, but no new memory rows.
    snapshot = {
        t: harness.memory_count(t) for t in ("concepts", "learner_observations", "memory_summary")
    }
    harness.mock_route({"match": "avoid making that sign mistake", "memory": skip_eval()})
    assert harness.wait_jobs_done(2) == ["done", "done"]
    assert {t: harness.memory_count(t) for t in snapshot} == snapshot
    skip_calls = [c for c in harness.mock_calls() if not c["stream"]]
    assert any("avoid making that sign mistake" in c["text"] for c in skip_calls)

    # --- Turn 3: captured memory survives the skip; kicks off job 3 ---
    reply3 = await chat_turn(e2e_client, token, chat_id, _TURN3)
    assert reply3.strip()
    turn3_call = harness.chat_calls()[-1]
    assert "LEARNER MEMORY CONTEXT" in turn3_call["text"]
    assert "Learner confuses the signs" in turn3_call["text"]  # survives the skip

    # Background worker: job 3 produces memory again → observations accumulate.
    harness.mock_route(
        {
            "match": "practice problem that needs the quadratic formula",
            "memory": memory_eval(
                observations=["Learner can now reliably keep signs straight when factoring."],
                updated_summary="Quadratic formula: signs are tracked well; pace is careful.",
            ),
        }
    )
    assert harness.wait_jobs_done(3) == ["done", "done", "done"]
    assert harness.memory_count("learner_observations") == 2
