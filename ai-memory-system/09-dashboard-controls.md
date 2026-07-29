# Task 09

## 1. Name

Memory Dashboard, Editing, and Debug Controls

## 2. Purpose in Bigger Picture

Make system inspectable during pilot. Diagnose false memories/retrieval. Allow recovery without database surgery.

## 3. Detailed Implementation Idea

Developer dashboard views:

- subject/topic/concept tree
- graph relations
- current learner state/scores
- evidence timeline
- Markdown version list/diff
- retrieval trace per turn
- job status/failures

Actions:

- correct concept mapping
- add/remove misconception
- correct state/trait
- rollback memory version
- retry/dead-letter job
- replay state from observations

Edits:

```text
user action
-> validated manual_override event
-> deterministic state update
-> new Markdown version
```

Never directly mutate historical observation/version. Store editor, reason, time.

Dashboard APIs should return structured data; UI formatting replaceable.

## 4. Success Criteria

- Developer traces current memory to supporting events.
- Version diff shows material change/reason.
- Retrieval view explains selection/exclusion.
- Manual correction creates override event + new version.
- Rollback preserves later audit history.
- Replay result matches stored state.
- Failed job visible/retryable.
- Editing child state refreshes affected rollup.
- Invalid concept/state edit rejected.

## 5. Gotchas

- Editing Markdown directly while structured state remains unchanged.
- Rollback interpreted as destructive deletion.
- Manual override later silently overwritten by weak inference.
- Dashboard showing scores without definitions.
- Exposing raw prompt/user-sensitive content unnecessarily.
- Retrieval traces growing without retention policy.
- Dashboard scope expanding into full student analytics product.

## 6. Related Concepts / Tasks

- Task 02 supplies audit data.
- Task 05 defines override precedence/replay.
- Task 06 supplies versions/diffs.
- Task 07 supplies retrieval traces.
- Task 03 supplies job controls.
- Student-facing memory UI remains later work; preserve API possibility.
