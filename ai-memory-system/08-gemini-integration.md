# Task 08

## 1. Name

Gemini Tutor and Learner-Brief Integration

## 2. Purpose in Bigger Picture

Use selected memory to change student-facing teaching behavior safely. Gemini remains sole conversational interface.

## 3. Detailed Implementation Idea

Request path:

```text
student input/image
-> normalize task facts/current attempt
-> Task 07 retrieval
-> compile learner brief
-> Gemini
-> save turn + normalized metadata
-> enqueue Task 03 job
```

Prompt layers:

```text
1. tutor policy
2. current problem/image facts
3. recent conversation
4. episode/session summary
5. learner brief
```

Learner brief:

```text
Relevant: confirmed strengths/difficulties
Verify: uncertain/stale claims
Tutor action: recommended help level/style
Avoid: over-help/full solution before attempt
```

Target 200–500 memory tokens. Structured state compiled deterministically; raw editable Markdown not injected.

Ask Gemini for sidecar metadata:

- concepts used
- help level given
- whether student attempted
- normalized image/student-work facts

Sidecar supports async extractor; never treated as student evidence by itself.

If retrieval/memory fails, Gemini responds normally. Memory is enhancement, not availability dependency.

## 4. Success Criteria

- Relevant learner brief appears in Gemini request only when useful.
- Brief stays within cap.
- No raw memory Markdown/user instructions passed as policy.
- Stale memory causes diagnostic, not asserted weakness.
- Known weak concept gets graduated hint before solution.
- Demonstrated strength prevents unnecessary explanation.
- Gemini still responds when retrieval/job system unavailable.
- Image turn stores enough normalized facts for background extraction.
- Completed turn queues exactly one memory job.
- Student-facing response never exposes internal scores unless requested.

## 5. Gotchas

- Memory contradicting current-turn evidence; current turn wins.
- Gemini overpersonalizing every response.
- Prompt layers mixing facts with instructions.
- Sidecar hallucination treated as learner evidence.
- Image interpretation omitted from extractor context.
- Retrieval latency degrading chat.
- Tutor policy accidentally encouraging answer leakage.

## 6. Related Concepts / Tasks

- Task 07 provides selection.
- Task 03 receives completed-turn job.
- Task 04 consumes normalized metadata.
- Task 06 memory format is not direct prompt format.
- Task 10 evaluates help calibration/answer leakage.
- Infinite chat not required; keep integration compatible with session summaries.
