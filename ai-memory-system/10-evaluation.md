# Task 10

## 1. Name

Evaluation and Regression Harness

## 2. Purpose in Bigger Picture

Prove memory helps without injecting false/stale context. Convert product behavior into repeatable coding/model tests.

## 3. Detailed Implementation Idea

Create 30–50 fake student histories with:

```text
turns
task/concept labels
expected observations/no-op
expected state transitions
expected retrieved memories
forbidden retrieved memories
expected tutor behavior rubric
```

Test layers separately:

1. Extractor: DeepSeek output vs labeled evidence.
2. Reducer: exact deterministic states.
3. Renderer: exact Markdown/version behavior.
4. Retrieval: expected/forbidden top results.
5. Gemini: behavioral rubric; diagnostic/help/answer leakage.
6. E2E: job -> state -> memory -> later response.

Core scenarios:

- ordinary question/no attempt
- self-reported weakness
- independent vs scaffolded success
- repeated misconception
- later recovery
- stale but previously mastered
- contradictory evidence
- cross-subject transfer
- irrelevant memory
- image-based attempt
- duplicate/out-of-order jobs
- manual correction

Store prompt/model/config versions with results. Run before changing extractor prompt, scoring, ontology, retrieval, or Gemini prompt.

## 4. Success Criteria

- All deterministic tests exact/repeatable.
- Golden no-op precision tracked.
- Unsupported observation rate tracked.
- Retrieval precision@3 and forbidden-hit rate tracked.
- Stale/incorrect injection rate tracked.
- Help rated too much/correct/too little.
- Answer-before-attempt rate tracked.
- Model regression report compares previous/current versions.
- Failed fixture shows stage and trace.
- E2E replay works from clean SQLite database.

## 5. Gotchas

- Only positive/easy histories.
- DeepSeek generating and judging same fixtures.
- Treating stochastic text equality as behavior test.
- Changing model alias without recording resolved model/version.
- Optimizing recall while false positives remain.
- Tests tied to exact prose instead of semantic behavior.
- “Vibed” histories missing recovery/conflict/no-op cases.

## 6. Related Concepts / Tasks

- Begin alongside Task 01.
- Tasks 04/05/07 require strongest fixtures.
- Task 08 needs tutoring rubric.
- Task 11 uses metrics as rollout gates.
- Priority: incorrect/stale injection, unsupported observations, precision@3, no-op accuracy, help calibration.
