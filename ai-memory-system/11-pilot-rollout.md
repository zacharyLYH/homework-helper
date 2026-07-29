# Task 11

## 1. Name

Pilot Integration and Rollout

## 2. Purpose in Bigger Picture

Connect components safely, observe real behavior, enable personalization only after memory quality proven.

## 3. Detailed Implementation Idea

Stages:

```text
1. Local golden histories.
2. Shadow extraction:
   create observations/state; no Gemini injection.
3. Dashboard review:
   inspect false writes, scoring, ontology gaps.
4. Shadow retrieval:
   log selected context; do not inject.
5. Limited injection:
   small users/subjects; feature flag.
6. Broader pilot after metric gates.
```

Model routing:

- Gemini: student response + image/task normalization.
- DeepSeek/OpenRouter: async observation extraction; optional ambiguous resolver.
- application: validation, scoring, retrieval, versioning.

Operational signals:

- queue age/failures
- OpenRouter/model errors
- extractor no-op/write rates
- versions per user/concept
- retrieval candidates/included
- memory token size
- Gemini latency delta
- manual correction rate

No historical backfill initially. Start learning from activation point; avoids low-quality bulk inference.

Feature flags:

- extraction
- state updates
- retrieval logging
- Gemini injection
- per user/subject

## 4. Success Criteria

- Full flow works on clean pilot user.
- Feature flags independently disable risky stages.
- Memory/provider failure never prevents normal Gemini chat.
- Shadow mode changes no student response.
- Limited injection respects token/selection caps.
- Metrics/dashboard expose harmful writes/retrieval.
- Rollback disables injection without deleting learned state.
- Queue recovers from temporary OpenRouter outage.
- Manual correction changes later Gemini behavior.
- Release gate based on Task 10 metrics, not anecdote alone.

## 5. Gotchas

- Enabling extraction and injection together; no baseline.
- Backfilling whole history with untested extractor.
- Model/provider aliases changing silently.
- Rollout limited by user but not subject/ontology coverage.
- Missing fallback when retrieval slow.
- Infinite-chat redesign mixed into pilot.
- Early metrics distorted by tiny concept ontology.

## 6. Related Concepts / Tasks

- Requires Tasks 01–08.
- Task 09 required for diagnosis/control.
- Task 10 defines gates.
- Keep current per-chat UX; infinite chat separate later project.
- Preserve collected observations across feature disable; stop injection independently.
