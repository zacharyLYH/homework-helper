# Task 03

## 1. Name

Async Memory Job Pipeline

## 2. Purpose in Bigger Picture

Analyze every completed turn without delaying Gemini response. Ensure retries, ordering, and duplicate safety.

## 3. Detailed Implementation Idea

After Gemini response saved:

```text
create memory job
return response
worker processes later
```

Job fields:

```text
job ID
user ID
turn ID
user sequence
status: queued | processing | retry | succeeded | dead
attempt count
next attempt time
prompt/extractor version
last error
timestamps
```

Worker behavior:

- FIFO per user
- multiple users may process concurrently
- claim job atomically
- call DeepSeek/OpenRouter outside DB transaction
- persist observations/state/version in short transaction
- mark success only after durable write
- retry transient provider/database failure
- dead-letter after configured attempts
- stale processing lease eventually reclaimable

Later job must not overtake failed earlier job for same user unless design explicitly supports replay from sequence.

## 4. Success Criteria

- Gemini response latency unaffected by extractor latency/outage.
- Two jobs for same user execute in turn order.
- Jobs for different users may execute concurrently.
- Retried job creates no duplicate observations/versions.
- Worker crash after model response safely retries.
- Worker crash after durable write safely resolves as completed.
- Provider rate limit causes retry, not data loss.
- Poison job reaches visible dead state; later behavior defined.
- Queue depth/age/failure count observable.

## 5. Gotchas

- Holding SQLite transaction during network call.
- Out-of-order state changes.
- At-least-once processing without idempotency.
- Job marked success before writes commit.
- Unlimited retries/cost.
- Editing extraction prompt without recording version.
- One failed user blocking every other user.

## 6. Related Concepts / Tasks

- Task 02 defines jobs/idempotency storage.
- Task 04 performs model extraction.
- Task 05/06 must commit atomically where practical.
- Task 08 creates jobs after student-facing turn.
- Task 11 monitors queue during rollout.
- Keep job payload references small; conversation remains canonical elsewhere.
