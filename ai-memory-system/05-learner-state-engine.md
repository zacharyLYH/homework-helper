# Task 05

## 1. Name

Deterministic Learner State Engine

## 2. Purpose in Bigger Picture

Turn noisy observations into stable mastery, independence, confidence, freshness, misconceptions, preferences. Same events must always produce same state.

## 3. Detailed Implementation Idea

Implement pure reducer:

```text
state = reduce(previous observations, scoring config)
```

Per concept:

```text
mastery
independence
confidence
freshness
status: unknown | struggling | developing | supported | independent
misconceptions
last demonstrated time
half-life
state version
```

Pilot scoring:

- outcome: incorrect=0, partial=.5, correct=1
- latest 12 qualifying weighted observations
- mastery = weighted outcome mean
- independence = no-help attempts only
- confidence grows with evidence; falls with contradiction
- evidence weight from observation kind × extractor confidence

Initial statuses:

```text
unknown: insufficient evidence
struggling: mastery < .40
developing: .40–.74
supported: mastery >= .75, independence < .60
independent: mastery >= .75, independence >= .60,
             >=2 independent successes
```

Hysteresis: 2 confirmations or threshold crossed by .10.

Freshness:

```text
exp(-ln(2) * days_since_success / half_life)
```

Start 30d; spaced independent success doubles; failed recall halves; clamp 7–180d. Time reduces freshness, not mastery.

Misconception: add after repeated/strong evidence; resolve after 2 targeted independent successes.

Preference: explicit immediate; inferred after 3 consistent signals; subject override above global.

All constants stored in versioned scoring config.

## 4. Success Criteria

- Replay same ordered events gives identical state.
- Independent success increases mastery/independence.
- Scaffolded success affects mastery less; not independence.
- Time passage changes freshness only.
- Contradiction lowers confidence, not automatic permanent weakness.
- Isolated answer does not flip stable status.
- Repeated misconception activates then resolves after recovery.
- Old errors can be overcome by newer consistent success.
- Preference scope override behaves predictably.
- Scoring config version identifies state calculation.

## 5. Gotchas

- False numerical precision.
- Negative evidence permanently dominating.
- Mastery and independence conflated.
- Freshness treated as proven forgetting.
- Time-dependent tests without fixed clock.
- Changing thresholds without replay/migration plan.
- Observation ordering differences.
- Manual override mixed invisibly with inference.

## 6. Related Concepts / Tasks

- Task 04 defines observations.
- Task 06 versions only material state changes.
- Task 07 uses confidence/freshness/status.
- Task 09 needs replay/explanation.
- Task 10 must test transitions/boundaries.
- Keep reducer independent from SQLite/provider APIs.
