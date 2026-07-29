# Task 07

## 1. Name

Concept Resolution and Memory Retrieval

## 2. Purpose in Bigger Picture

Find small, precise learner context for current homework before Gemini answers. Avoid entire-memory prompt dumps.

## 3. Detailed Implementation Idea

Resolution:

```text
explicit task/course metadata
-> exact canonical name/ID
-> alias lookup
-> SQLite FTS candidates
-> optional cheap DeepSeek rerank/classification
```

DeepSeek receives candidate IDs/descriptions; cannot invent active IDs. Unknown remains `unclassified` or concept proposal.

Graph expansion:

- exact concept
- direct prerequisites required by task
- closely related/application concepts
- one parent rollup
- relevant cross-cutting skills/preferences

Ranking starter:

```text
45% task relevance
25% memory confidence
20% instructional usefulness
10% freshness
```

Overrides:

- exact before related
- prerequisite only if needed and weak/stale
- confidence below .55 excluded unless exact
- contradicted/low-freshness memory marked `verify`

Caps:

- 3 direct/related
- 2 prerequisites
- 1 parent
- 1 learner profile

Return structured selection + reasons. Save retrieval trace. Vector search deferred; later candidate recall only.

## 4. Success Criteria

- Exact concept query retrieves exact learner state.
- Alias query resolves same concept.
- Cross-subject application retrieves shared concept.
- Weak required prerequisite included.
- Irrelevant siblings excluded.
- Low-confidence non-direct memory excluded.
- Stale exact memory returned as verification need.
- Unknown wording does not create concept automatically.
- Candidate cap always respected.
- Retrieval trace explains included/excluded candidates.
- Golden queries reach agreed precision@3.

## 5. Gotchas

- Graph expansion explosion.
- Similar wording != same concept.
- Using FTS/vector score as truth.
- Retrieval based on weakness only; strengths also affect help.
- Parent rollup duplicating child detail.
- DeepSeek classification adding response latency; use only ambiguous path.
- Current assignment context more reliable than inferred subject.

## 6. Related Concepts / Tasks

- Task 01 graph/aliases.
- Task 05 supplies confidence/freshness.
- Task 06 supplies current views.
- Task 08 compiles selection for Gemini.
- Task 09 visualizes traces.
- Task 10 owns retrieval fixtures.
- Keep retrieval interface independent from future vector backend.
