"""Topic-graph propagation organic test.

The memory graph stores prerequisite edges between concepts. Context loading
(``load_memory_context``) surfaces, for every weak concept (mastery < 0.5),
the concepts that point into it via ``prerequisite`` edges — rendered as
"Prerequisites to reinforce: - <from> → <to>".

This test drives the full loop organically with the background worker:

  1. chats enqueue real jobs
  2. a worker evaluation establishes a **topic node** ("Quadratics", the
     upstream concept) plus three **downstream leaf concepts** (formula,
     factoring, discriminant) with prerequisite edges topic → leaf
  3. a second evaluation mutates the topic node's learner state (re-teach
     cycle: mastery drops) and adds a *new* downstream concept with an edge
  4. chat turns verify that every weak downstream concept pulls the topic
     into its context's prerequisite section, and that the graph edits
     survived (edge upsert re-writes, no duplicates)

Determinism rules with the live worker: eval routes are registered BEFORE the
turn that enqueues the matching job, and waits are absolute (">= N terminal").
"""

from __future__ import annotations

import httpx

from .harness import Harness, chat_turn, create_chat, memory_eval

TOPIC = "quadratics"
TOPIC_NAME = "Quadratics"
LEAVES = ("quadratic_formula", "factoring_quadratics", "discriminant")
LEAF_NAMES = {
    "quadratic_formula": "Quadratic Formula",
    "factoring_quadratics": "Factoring Quadratics",
    "discriminant": "Discriminant",
}
NEW_LEAF = "completing_the_square"
NEW_LEAF_NAME = "Completing the Square"

HOMEWORK_MSG = (
    "For my algebra homework, can you help me practice {concept} step by step?"
)


async def _memory_context(client: httpx.AsyncClient, token: str, subject_id: int) -> str:
    r = await client.get(
        f"/api/memory/subjects/{subject_id}/context", headers=Harness.auth(token)
    )
    r.raise_for_status()
    return str(r.json()["memory_context"])


async def test_memory_topic_graph_propagation(
    harness: Harness, e2e_client: httpx.AsyncClient
) -> None:
    token = harness.register_user("ivy@school.edu")
    harness.seed_llm_config(token)
    r = await e2e_client.post("/api/subjects", params={"name": "Math"}, headers=Harness.auth(token))
    r.raise_for_status()
    subject_id = int(r.json()["id"])
    chat_id = await create_chat(e2e_client, token, subject_id)

    # Route turn 1's eval BEFORE the turn (the worker may claim instantly):
    # establish the topic node + 3 downstream leaves in one evaluation; edges
    # point topic → leaf (the topic is the prerequisite for each leaf).
    harness.mock_route(
        {
            "match": "quadratic equations",
            "memory": memory_eval(
                observations=["Learner is starting a quadratics unit in algebra homework."],
                concept_upserts=[{"concept_key": TOPIC, "display_name": TOPIC_NAME, "aliases": []}]
                + [
                    {"concept_key": leaf, "display_name": LEAF_NAMES[leaf], "aliases": []}
                    for leaf in LEAVES
                ],
                concept_edges=[
                    {
                        "from_concept_key": TOPIC,
                        "to_concept_key": leaf,
                        "relation": "prerequisite",
                        "weight": 0.9,
                    }
                    for leaf in LEAVES
                ],
                concept_state_deltas=[{"concept_key": TOPIC, "mastery": 0.8, "confidence": 0.9}]
                + [{"concept_key": leaf, "mastery": 0.4, "confidence": 0.9} for leaf in LEAVES],
                updated_summary="Learner is beginning quadratics; downstream skills still shaky.",
            ),
        }
    )

    # --- Turn 1: homework turn enqueues a job; no memory yet ---
    reply = await chat_turn(
        e2e_client, token, chat_id, HOMEWORK_MSG.format(concept="quadratic equations")
    )
    assert reply.strip()
    assert harness.wait_jobs_done(1) == ["done"]
    assert harness.memory_count("concepts") == 4  # topic + 3 leaves
    assert harness.memory_count("concept_edges") == 3  # topic → each leaf

    # Weak leaves (0.4 < 0.5) must already pull the topic into prerequisites.
    ctx = await _memory_context(e2e_client, token, subject_id)
    assert "Prerequisites to reinforce" in ctx
    for leaf_name in LEAF_NAMES.values():
        assert f"- {TOPIC_NAME} → {leaf_name}" in ctx, ctx

    # Route turn 2's eval, then turn: memory context reaches the model and the
    # worker mutates the topic node + grows the graph (re-teach cycle: topic
    # mastery drops 0.8 → 0.3, a new leaf joins, the topic→formula edge is
    # re-upserted with a new weight).
    harness.mock_route(
        {
            "match": "the discriminant",
            "memory": memory_eval(
                observations=["Learner regressed on quadratics after the re-teach cycle."],
                concept_upserts=[
                    {"concept_key": TOPIC, "display_name": TOPIC_NAME, "aliases": ["quad eqs"]},
                    {"concept_key": NEW_LEAF, "display_name": NEW_LEAF_NAME, "aliases": []},
                ],
                concept_edges=[
                    {
                        "from_concept_key": TOPIC,
                        "to_concept_key": "quadratic_formula",
                        "relation": "prerequisite",
                        "weight": 1.0,
                    },
                    {
                        "from_concept_key": TOPIC,
                        "to_concept_key": NEW_LEAF,
                        "relation": "prerequisite",
                        "weight": 0.8,
                    },
                ],
                concept_state_deltas=[
                    {"concept_key": TOPIC, "mastery": 0.3, "confidence": 0.85},
                    {"concept_key": NEW_LEAF, "mastery": 0.1, "confidence": 0.9},
                ],
                updated_summary="Quadratics re-teach cycle: topic shaky, completing the square new.",
            ),
        }
    )
    await chat_turn(
        e2e_client, token, chat_id, HOMEWORK_MSG.format(concept="the discriminant")
    )
    call = harness.chat_calls()[-1]
    assert "LEARNER MEMORY CONTEXT" in call["text"]
    assert f"{TOPIC_NAME} → Discriminant" in call["text"]
    assert harness.wait_jobs_done(2) == ["done", "done"]

    # Graph grew without duplication: 5 concepts, 4 distinct edges (the
    # topic→formula edge was upserted in place, not duplicated).
    assert harness.memory_count("concepts") == 5
    assert harness.memory_count("concept_edges") == 4
    rows = harness.sql(
        "memory",
        """
        SELECT cf.concept_key AS f, ct.concept_key AS t, ce.weight AS w
        FROM concept_edges ce
        JOIN concepts cf ON ce.from_concept_id = cf.id
        JOIN concepts ct ON ce.to_concept_id = ct.id
        WHERE ce.relation = 'prerequisite'
        """,
    )
    edge_map = {(row["f"], row["t"]): row["w"] for row in rows}
    assert edge_map[(TOPIC, "quadratic_formula")] == 1.0  # weight mutated, not duplicated
    assert edge_map[(TOPIC, NEW_LEAF)] == 0.8

    # Topic node itself became weak (0.3 < 0.5) → it now appears in weak
    # concepts alongside all downstream leaves.
    ctx = await _memory_context(e2e_client, token, subject_id)
    assert f"{TOPIC_NAME} (mastery: 0.30)" in ctx
    assert f"{NEW_LEAF_NAME} (mastery: 0.10)" in ctx

    # Every weak downstream leaf still pulls the mutated topic node in.
    for leaf_name in (*LEAF_NAMES.values(), NEW_LEAF_NAME):
        assert f"- {TOPIC_NAME} → {leaf_name}" in ctx, ctx

    # Route turn 3's eval, then turn: the mutated graph reaches the model.
    harness.mock_route(
        {
            "match": "completing the square",
            "memory": memory_eval(
                concept_upserts=[
                    {"concept_key": "word_problems", "display_name": "Word Problems", "aliases": []}
                ],
                concept_edges=[
                    {
                        "from_concept_key": "ghost_concept",
                        "to_concept_key": "word_problems",
                        "relation": "related",
                        "weight": 0.5,
                    }
                ],
                concept_state_deltas=[
                    {"concept_key": "word_problems", "mastery": 0.6, "confidence": 0.7}
                ],
                updated_summary="Learner practicing quadratics word problems.",
            ),
        }
    )
    await chat_turn(
        e2e_client, token, chat_id, HOMEWORK_MSG.format(concept="completing the square")
    )
    call = harness.chat_calls()[-1]
    assert "LEARNER MEMORY CONTEXT" in call["text"]
    assert f"{TOPIC_NAME} (mastery: 0.30)" in call["text"]
    assert f"{TOPIC_NAME} → Completing the Square" in call["text"]

    # --- Sad path: an edge to an unknown concept is dropped, job still done ---
    assert harness.wait_jobs_done(3) == ["done", "done", "done"]
    assert harness.memory_count("concepts") == 6  # word_problems added, ghost not
    assert harness.memory_count("concept_edges") == 4  # unchanged: ghost edge skipped
