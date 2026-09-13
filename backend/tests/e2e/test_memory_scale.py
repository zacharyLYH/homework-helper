"""Scale + isolation organic test: 120 loops across multiple scopes.

Six scopes (2 users × 3 subjects) each run 20 chat turns — 120 chat turns and
120 memory jobs total — processed by the real background worker loop (its own
process, production shape). Tests never crank the worker: they chat, route
content-keyed eval specs for the worker's LLM, and wait for the queue to drain.

Routing keys: every turn uses alignment-gate-safe homework text. Round 1 gives
each scope one distinct (but gate-proven) message so the worker evals can be
routed per scope; later rounds are routed on the scope's previous summary —
unique per (user, subject) and present only in that scope's eval prompt.

What it pins down:
  * scale — 100+ jobs flow through the real queue + worker process without loss
  * accumulation — observations append, concepts/states/traits/summaries
    accumulate per scope across loops
  * isolation — nothing leaks between (user, subject) scopes; the sharpest
    check is cross-user same-subject-name (ada vs bo, both "Math")
  * concurrency — round 1 races the alignment encoder cold-start on the
    backend (thread-safe + warmed at startup; it crashed the process before)
"""

from __future__ import annotations

import asyncio
import json

import httpx

from .harness import Harness, chat_turn, create_chat, create_subject, memory_eval

USERS = ("ada@school.edu", "bo@school.edu")
SUBJECTS = ("Math", "Physics", "Economics")
ROUNDS = 20  # chat turns (and memory jobs) per scope

# The workhorse message: alignment-gate-proven homework text (same family as
# the organic loop test). Shared by all scopes for every round after the first.
_MSG_SHARED = (
    "For my algebra homework, I keep making sign mistakes in the quadratic formula"
)

# Round-1 messages: one per scope. All are distinct strings (so round-1 evals
# can be routed per scope) and all verified against the real alignment gate
# (embedding similarity to the homework corpus >= 0.46, threshold is 0.4).
_ROUND1_MSGS = (
    "For my algebra homework, I keep making sign mistakes when I factor quadratics",
    "For my algebra homework, I keep making mistakes in my word problem steps",
    "For my algebra homework, I keep making arithmetic mistakes completing the square",
    "For my algebra homework, I keep making sign mistakes when I simplify fractions",
    "For my algebra homework, I keep making mistakes in my graphing steps",
    "For my algebra homework, I keep making mistakes in my system of equations steps",
)


def email_for(user_tag: str) -> str:
    return f"{user_tag}@school.edu"


def _scopes() -> list[tuple[str, str, str, str]]:
    """(email, user_tag, subject, round1_message) in creation order."""
    return [
        (email, email.split("@")[0], subject, _ROUND1_MSGS[i])
        for i, (email, subject) in enumerate(
            (email, subject) for email in USERS for subject in SUBJECTS
        )
    ]


def _concept_for(user_tag: str, subject: str, n: int) -> str:
    return f"{user_tag}-{subject}-topic-{n % 10}"


def _observation_for(user_tag: str, subject: str, n: int) -> str:
    return f"{user_tag} in {subject}: struggled with {_concept_for(user_tag, subject, n)}"


def _summary_for(user_tag: str, subject: str, n: int) -> str:
    return f"{user_tag} {subject} summary version {n}"


def _trait_key_for(user_tag: str, subject: str) -> str:
    return f"prefers_{user_tag}_{subject}"


def _producing_for(user_tag: str, subject: str, n: int) -> dict:
    """A producing evaluation unique to one (user, subject, round)."""
    return memory_eval(
        observations=[_observation_for(user_tag, subject, n)],
        concept_upserts=[
            {
                "concept_key": _concept_for(user_tag, subject, n),
                "display_name": _concept_for(user_tag, subject, n),
                "aliases": [],
            }
        ],
        concept_state_deltas=[
            {
                "concept_key": _concept_for(user_tag, subject, n),
                "mastery": 0.2 + (n % 5) * 0.1,
                "confidence": 0.8,
            }
        ],
        trait_updates={_trait_key_for(user_tag, subject): f"loop-{n}"},
        updated_summary=_summary_for(user_tag, subject, n),
    )


def _routes_for_round(
    scopes: dict[tuple[str, str], tuple[str, int, int, str]], n: int
) -> list[dict]:
    """One content-routed eval spec per scope for round ``n``.

    Round 1 matches the scope's unique round-1 message; later rounds match the
    scope's previous summary (present only in that scope's eval prompt).
    """
    routes = []
    for (user_tag, subject), (_tok, _sid, _chat, msg1) in scopes.items():
        match = msg1 if n == 1 else _summary_for(user_tag, subject, n - 1)
        routes.append({"match": match, "memory": _producing_for(user_tag, subject, n)})
    return routes


async def _turn(
    client: httpx.AsyncClient, token: str, chat_id: int, message: str
) -> None:
    """chat_turn, ignoring the reply text (the mock streams a default reply)."""
    await chat_turn(client, token, chat_id, message)


async def _scope_context(
    client: httpx.AsyncClient, token: str, subject_id: int
) -> str:
    r = await client.get(
        f"/api/memory/subjects/{subject_id}/context", headers=Harness.auth(token)
    )
    r.raise_for_status()
    return str(r.json()["memory_context"])


def _section_items(ctx: str, header: str) -> list[str]:
    """The '- ' items under one rendered context section header."""
    for section in ctx.split("\n\n"):
        if section.startswith(header):
            return [line[2:] for line in section.splitlines()[1:]]
    return []


async def test_memory_scale_many_loops_and_scope_isolation(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    scopes: dict[tuple[str, str], tuple[str, int, int, str]] = {}
    for email, user_tag, subject, msg1 in _scopes():
        token = harness.register_user(email)
        harness.seed_llm_config(token)
        subject_id = await create_subject(e2e_client, token, subject)
        chat_id = await create_chat(e2e_client, token, subject_id)
        scopes[(user_tag, subject)] = (token, subject_id, chat_id, msg1)

    user_id_by_email = {
        str(r["email"]): int(r["id"])
        for r in harness.sql("app", "SELECT id, email FROM users")
    }

    total_scopes = len(scopes)
    total_jobs = total_scopes * ROUNDS

    # --- Phase 1+2: 20 rounds; each round = one concurrent turn per scope +
    # a drain. The dedup heuristic skips a turn when its scope already has a
    # pending job, so the test drains between rounds (production keeps up with
    # traffic too). Routes go in BEFORE the turns — the worker may claim a job
    # the instant it is enqueued.
    for n in range(1, ROUNDS + 1):
        harness.mock_route(_routes_for_round(scopes, n))
        await asyncio.gather(
            *(
                _turn(e2e_client, token, chat_id, msg1 if n == 1 else _MSG_SHARED)
                for (user_tag, subject), (token, _sid, chat_id, msg1) in scopes.items()
            )
        )
        # Absolute wait: all jobs so far (n rounds × one per scope) are done.
        statuses = harness.wait_jobs_done(total_scopes * n)
        assert all(s == "done" for s in statuses), statuses

    # --- Phase 3: accumulation within each scope ---
    assert len(harness.job_statuses()) == total_jobs
    assert set(harness.job_statuses()) == {"done"}
    # Observations append once per producing job (all 120 rounds).
    assert harness.memory_count("learner_observations") == total_jobs
    # 10 distinct concepts per scope (round n reuses concept n % 10).
    assert harness.memory_count("concepts") == total_scopes * 10
    # One state row per (scope, concept).
    assert harness.memory_count("learner_concept_state") == total_scopes * 10
    # One summary + one traits row per scope (last write wins).
    assert harness.memory_count("memory_summary") == total_scopes
    assert harness.memory_count("learner_traits") == total_scopes

    for (user_tag, subject), (token, subject_id, _chat, _m1) in scopes.items():
        ctx = await _scope_context(e2e_client, token, subject_id)
        # The scope's own latest summary + merged trait survived all 20 rounds.
        assert _summary_for(user_tag, subject, ROUNDS) in ctx, ctx
        assert f"{_trait_key_for(user_tag, subject)}: loop-{ROUNDS}" in ctx, ctx
        # Recent observations (last 3 by recency) are this scope's latest.
        for n in (ROUNDS, ROUNDS - 1, ROUNDS - 2):
            assert _observation_for(user_tag, subject, n) in ctx, ctx

    # --- Phase 3.5: the injected block stays bounded at scale ---
    # After 20 rounds each scope has 20 observations and 6 weak concepts
    # (final masteries cycle: 0.2/0.3/0.4 are weak, 0.5/0.6 are not). The
    # context must show the caps, not the history: 3 obs, 5 weak concepts,
    # and a hard ceiling on rendered size.
    for (user_tag, subject), (token, subject_id, _chat, _m1) in scopes.items():
        ctx = await _scope_context(e2e_client, token, subject_id)
        obs_items = _section_items(ctx, "Recent learner observations:")
        weak_items = _section_items(ctx, "Weak concepts:")
        assert len(obs_items) == 3, (user_tag, subject, obs_items)
        assert len(weak_items) == 5, (user_tag, subject, weak_items)
        # ~950 chars in practice; the ceiling catches unbounded-growth
        # regressions (e.g. rendering all observations instead of 3).
        assert len(ctx) < 2000, (user_tag, subject, len(ctx))

    # Every chat turn and explicit fetch logs one retrieval trace: 120 turns
    # + 12 explicit context fetches (Phase 3 + 3.5) so far. The latest trace
    # per scope records post-LIMIT result counts, matching the rendered caps.
    # (ORDER BY id explicitly: the scope index scans created_at DESC, so bare
    # SELECTs return newest-first.)
    for (user_tag, subject), (_token, subject_id, _chat, _m1) in scopes.items():
        rows = harness.sql(
            "memory",
            """
            SELECT result_json FROM retrieval_traces
            WHERE user_id = ? AND subject_id = ? ORDER BY id
            """,
            (user_id_by_email[email_for(user_tag)], subject_id),
        )
        assert len(rows) == ROUNDS + 2, (user_tag, subject, len(rows))
        counts = json.loads(str(rows[-1]["result_json"]))
        assert counts["weak_concept_count"] == 5
        assert counts["obs_count"] == 3

    # --- Phase 4: isolation — scopes never leak into each other ---
    for (user_tag, subject), (token, subject_id, _chat, _m1) in scopes.items():
        ctx = await _scope_context(e2e_client, token, subject_id)
        for (other_tag, other_subject) in scopes:
            if (other_tag, other_subject) == (user_tag, subject):
                continue
            assert _summary_for(other_tag, other_subject, ROUNDS) not in ctx
            assert _trait_key_for(other_tag, other_subject) not in ctx
            for n in (1, 10, ROUNDS):
                assert _observation_for(other_tag, other_subject, n) not in ctx

    # Cross-user, same subject name is the sharpest isolation check.
    ada_ctx = await _scope_context(e2e_client, *scopes[("ada", "Math")][:2])
    bo_ctx = await _scope_context(e2e_client, *scopes[("bo", "Math")][:2])
    assert "ada" in ada_ctx and "bo" not in ada_ctx, ada_ctx
    assert "bo" in bo_ctx and "ada" not in bo_ctx, bo_ctx

    # --- Phase 5: a new turn in one scope sees its memory; nothing else leaks ---
    harness.mock_reset()
    token, subject_id, chat_id, _m1 = scopes[("ada", "Math")]
    await chat_turn(e2e_client, token, chat_id, _MSG_SHARED)
    call = harness.chat_calls()[-1]
    assert "LEARNER MEMORY CONTEXT" in call["text"]
    assert _summary_for("ada", "Math", ROUNDS) in call["text"]
    assert _trait_key_for("bo", "Physics") not in call["text"]
    harness.wait_jobs_done(total_jobs + 1)  # the new job drains via organic skip
