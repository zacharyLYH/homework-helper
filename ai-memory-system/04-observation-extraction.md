# Task 04

## 1. Name

Structured Observation Extraction

## 2. Purpose in Bigger Picture

Convert conversation behavior into narrow, auditable evidence. Main protection against false memories.

## 3. Detailed Implementation Idea

Use DeepSeek via OpenRouter. Input:

- current user message/attempt
- Gemini reply
- normalized task facts
- resolved concept candidates
- assistance already given
- minimal state only when needed

For image tasks, Gemini supplies normalized task/student-work transcription. Extractor must not guess unseen image details.

Output 0..N observations:

```text
concept ID
outcome: correct | partial | incorrect | unknown
reasoning: strong | partial | flawed | absent
assistance: none | prompt | concept_hint | scaffold | worked_answer
misconception key?
preference signal?
confidence
source evidence location
```

Validator:

- schema/enum checks
- concept ID exists
- evidence belongs to student, not Gemini
- assistance/outcome combination plausible
- confidence threshold
- unsupported output discarded

Explicit rules:

- asking question/requesting answer = no mastery evidence
- self-reported weakness = hypothesis
- success after worked answer = zero mastery
- assistant explanation = never student mastery
- most turns should return empty list

Record extractor model/prompt/schema version.

## 4. Success Criteria

- Golden no-op turns emit zero observations.
- Independent correct explanation emits positive evidence.
- Scaffolded correctness records assistance; not independent mastery.
- Repeated misconception uses stable misconception key.
- Self-report becomes hypothesis, not confirmed weakness.
- Gemini answer never attributed to student.
- Malformed/unknown concept output rejected.
- Same fixtures remain within agreed variance across repeated runs.
- Image fixture uses normalized student work; missing data yields no inference.
- Prompt-injection text cannot make extractor alter schema/rules.

## 5. Gotchas

- Extractor eager to produce useful-looking memories.
- Giving full history causes context rot/bias.
- Prior state anchoring new judgment.
- Prompt/model upgrades silently changing behavior.
- Confidence used as substitute for evidence.
- One observation spanning multiple concepts without clear attribution.
- Inferring personality/identity instead of behavior.

## 6. Related Concepts / Tasks

- Task 01 supplies allowed concept IDs.
- Task 03 invokes extractor.
- Task 05 consumes normalized observations only.
- Task 08 supplies normalized task/image facts and help level.
- Task 10 owns golden extraction fixtures.
- Future model replacement must preserve output contract.
