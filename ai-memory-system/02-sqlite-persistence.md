# Task 02

## 1. Name

SQLite Persistence Model

## 2. Purpose in Bigger Picture

Durable source for evidence, current learner state, versioned Markdown, async jobs, retrieval/debug traces. Must support deterministic replay and manual correction.

## 3. Detailed Implementation Idea

SQLite tables:

```text
concepts
concept_aliases
concept_edges

learner_observations
learner_concept_state
learner_traits

memory_versions
memory_current

memory_update_jobs
retrieval_traces
```

Storage rules:

- observations immutable
- memory versions immutable
- current state replaceable only through aggregator/manual override
- `memory_current` points to latest version
- manual edit/rollback appends event + version; never erases history
- job idempotency key based on completed turn
- state rows versioned for optimistic update

Important indexes:

- user + concept
- user + observation time
- job status + sequence
- memory scope + current version
- concept aliases/search text

Use transactions for:

- observation insert + state update
- state update + material memory version
- job completion after durable changes

SQLite permits one writer at a time. Keep write transactions short. Application-level per-user ordering still required.

## 4. Success Criteria

- Fresh database migration creates all tables/constraints.
- Duplicate job/event idempotency key produces no duplicate effect.
- Historical observations/versions cannot be accidentally overwritten.
- State can rebuild solely from active concept config + observations.
- Current memory pointer always references existing version.
- Failed transaction leaves no partial observation/state/version.
- Manual edit and rollback preserve complete history.
- Representative user/concept queries use expected indexes.

## 5. Gotchas

- Storing canonical facts only inside Markdown.
- Long model calls inside DB transaction.
- JSON blobs for fields needing query/filter.
- Missing foreign-key behavior for retired concepts.
- Relying on SQLite write serialization for logical turn order.
- Schema unable to distinguish inferred evidence vs manual override.
- Deleting old versions too early.

## 6. Related Concepts / Tasks

- Task 03 owns job lifecycle/order.
- Task 05 owns state calculations.
- Task 06 owns memory version creation.
- Task 09 relies on observations/versions/traces.
- Task 10 needs replayable fixtures.
- Schema should allow later migration from SQLite without changing domain contracts.
