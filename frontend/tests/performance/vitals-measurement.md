# Web Vitals in Interaction Tests — Findings & Suggestions

## Current Behavior

`frontend/tests/performance/vitals.ts` installs `PerformanceObserver` listeners on page load and accumulates CLS and INP in a single `window.__vitals` object for the **entire page lifespan**.

`frontend/tests/performance/interactions.spec.ts`:
1. Navigates to a page and waits for LCP to confirm initial render completed.
2. Performs interactions (clicks, typing, drawing).
3. Reads `window.__vitals` and asserts against `GOOD` thresholds (`inpMs: 200`, `cls: 0.1`).

## Core Issue

The tests are measuring **cumulative** values (page load + interactions), not interaction-specific deltas. This means:

- A slow INP from initial hydration can mask or conflate with interaction latency.
- You cannot tell whether a violation came from the app booting or from the user action under test.
- INP is tracked as a single maximum duration — not a per-event list — so there's no way to attribute a slow value to a specific interaction.

## Suggestions

### 1. Use baseline snapshots (CLS especially)

Take a snapshot of `__vitals` after LCP fires (post-hydration), then compute the delta after interactions:

```typescript
const baseline = await readVitals(page);
// ... interactions ...
const after = await readVitals(page);
const clsDelta = after.cls - baseline.cls;
expect(clsDelta).toBeLessThanOrEqual(0.05);
```

CLS is cumulative and unambiguous — the delta cleanly represents layout shifts introduced by the interaction phase.

### 2. Track individual event durations for INP

Replace the single-max INP tracker with an array of event durations. During the interaction phase, assert that no single event exceeds a threshold:

```typescript
const events: number[] = [];
new PerformanceObserver((list) => {
  for (const e of list.getEntries()) {
    if (e.entryType === "event" && e.duration >= 16) {
      events.push(e.duration);
    }
  }
}).observe({ type: "event", buffered: true, durationThreshold: 16 });
```

This lets you verify "no interaction event took longer than X ms" rather than relying on a global maximum.

### 3. Consider `web-vitals` npm package

The [`web-vitals`](https://github.com/GoogleChrome/web-vitals) package implements the spec correctly (e.g., INP as a 98th-percentile over the session). Using `onINP` / `onCLS` with `reportAllChanges: true` gives you accurate incremental deltas without hand-rolled `PerformanceObserver` logic.

### 4. Keep first-render and interaction tests separate

Don't mix LCP/FCP assertions with interaction-phase assertions. The current tests do both in one flow, which makes violations hard to attribute.

---

## Summary

The current approach is a pragmatic approximation and catches worst-case regressions, but it conflates load-time and interaction-time metrics. Baseline snapshots for CLS and per-event tracking for INP would give you precise, attributable measurements without significantly increasing test complexity.
