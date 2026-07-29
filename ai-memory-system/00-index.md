# Learner Memory: Task Index

Source spec: [../ai-memory-system.md](../ai-memory-system.md)

## Model Roles

- Gemini: all student-facing conversation; image understanding; consumes learner brief.
- DeepSeek via OpenRouter: cheap background extraction; optional ambiguous concept classification; non-student-facing generation.
- Deterministic application code: validation, scoring, state transitions, ranking, version gates. Models never own canonical scores.
- SQLite: concept graph, observations, current state, jobs, Markdown versions, debug traces.

## Recommended Order

```text
01 Concept Model
  -> 02 SQLite Storage
       -> 03 Async Jobs
       -> 04 Observation Extractor
            -> 05 Learner State Engine
                 -> 06 Markdown Memory
01 + 05 + 06
  -> 07 Retrieval
       -> 08 Gemini Integration
02 + 06 + 07
  -> 09 Dashboard
All tasks
  -> 10 Evaluation
  -> 11 Pilot Rollout
```

Evaluation fixtures should start during Tasks 01–04, not only after implementation.

## Tasks

1. [Concept Model and Pilot Ontology](01-concept-model.md)
2. [SQLite Persistence Model](02-sqlite-persistence.md)
3. [Async Memory Job Pipeline](03-async-memory-jobs.md)
4. [Observation Extraction](04-observation-extraction.md)
5. [Learner State Engine](05-learner-state-engine.md)
6. [Markdown Memory and Versioning](06-markdown-memory.md)
7. [Concept Resolution and Retrieval](07-retrieval.md)
8. [Gemini Tutor Integration](08-gemini-integration.md)
9. [Memory Dashboard and Controls](09-dashboard-controls.md)
10. [Evaluation and Regression Harness](10-evaluation.md)
11. [Pilot Integration and Rollout](11-pilot-rollout.md)
