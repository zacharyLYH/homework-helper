# 12 — Reconciliation: Design vs. Implementation vs. Roadmap

Companion to `00-index.md`. Reconciles the statistical memory engine specified in
`ai-memory-system.md` (root spec) with the simplified implementation that
shipped in `backend/memory/`, and proposes the highest-leverage improvements.

## 0. TL;DR

- **Design (spec):** LLM extracts structured, weighted observations; a *deterministic*
  reducer computes mastery/independence/confidence/freshness + status/hysteresis;
  retrieval ranks by relevance/confidence/usefulness/freshness; memories are
  versioned Markdown with a material-change gate. *"Models never own canonical scores."*
  (`00-index.md:9`, `ai-memory-system.md:46`)
- **Implementation (`backend/memory/`):** LLM writes **absolute** mastery directly
  (`memory/jobs/utils.py:320-329`, `memory/llm.py:136`); no freshness/decay; no
  observation contract; no status/hysteresis; no Markdown versioning; flat single-level
  `concepts` + `memory_summary`. The simplification is real and measurable.
- **Best single lever:** restore extraction ↔ aggregation separation + BKT mastery
  (4 params, closed-form — realistic under limited data/compute), so mastery is
  *derived* from auditable evidence rather than guessed. IRT is the aspirational
  upgrade once labeled outcomes exist.

---

## 1. What the shipped code actually implements

| Concern | Spec (design) | Code (`backend/memory/`) |
|---|---|---|
| Concept identity | `subject → topic → concept` hierarchy; `parent_of`, `prerequisite_of`, `related_to`, `applied_in`, `alias_of` (`01-concept-model.md`, `ai-memory-system.md:83-95,159-163,478-486`) | Flat `concepts` table scoped only by `subject_id`; single `prerequisite`/`related` relation (`db.py:8-30`). No topics/skills/parent_of/applied_in. |
| Observation model | Structured contract: outcome/reasoning/assistance/misconception/confidence/evidence loc (`04-observation-extraction.md:27-35`) | Free-text `learner_observations.observation` string only (`db.py:39`). No outcome/assistance/confidence fields. |
| Observation weights | `+3 correct transfer`, `+2 independent correct`, `+1 hint`, `-2 independent incorrect`, `-3 repeated misconception`, × extractor confidence (`ai-memory-system.md:247-259`) | None. `enqueue_memory_update` skip heuristics exist, but no weighted-outcome scoring (`memory/service/main.py:189`). |
| Evidence rules | "ask/answer = no evidence"; "correct after worked answer = no mastery"; self-report = hypothesis; repeated misconception stronger; never attribute assistant output to student (`04-observation-extraction.md:46-53`, `ai-memory-system.md:232-243`) | Not enforced. Worker LLM may emit observations for any text. |
| Mastery | Weighted mean of latest 12 qualifying observations; outcome y ∈ {0,.5,1} × weight × confidence (`ai-memory-system.md:280-287`) | LLM writes **absolute** mastery (`jobs/utils.py:320-329`, `llm.py:136`, `schemas.py:29`). `mastery = excluded.mastery` from LLM JSON. **Directly violates** "models never own canonical scores." |
| Independence | Weighted mean over no-help attempts only (`ai-memory-system.md:284`) | No `independence` field at all. |
| Confidence | Grows with evidence count; falls on contradiction (`ai-memory-system.md:285`) | Per-concept `confidence` column exists (`db.py:52`) but is LLM-supplied, not derived. |
| Freshness / decay | `exp(-ln2 * days_since_demo / half_life)`; half-life 30d start, double on spaced success, halve on failed recall, clamp 7–180d; **never decays mastery** (`ai-memory-system.md:308-323`, `05-learner-state-engine.md:55-61`) | No freshness concept. `learner_concept_state` has only `mastery, confidence, updated_at` (`db.py:46-56`). |
| Status | `unknown | struggling | developing | supported | independent` (`ai-memory-system.md:291-298`) | No `status` column. |
| Hysteresis | 2 confirmations OR threshold crossed by ≥0.10 (`ai-memory-system.md:302-306`) | None. |
| Misconceptions | Add after 2 same-pattern attempts or strong evidence; resolve after 2 independent correct (`ai-memory-system.md:338-341`) | No `misconceptions` storage; not extracted/validated/resolved. |
| Preferences | Explicit immediate; inferred after 3 consistent signals; subject-scope override + global fallback (`ai-memory-system.md:343-347`) | Single `traits_json` blob (`db.py:60-67`), LLM-written, no confidence/scope fallback. |
| Material-change gate | Version only on status/misconception/independence/preference/strategy/manual (`ai-memory-system.md:349-366`) | N/A — no versioning at all. |
| Markdown memory + versioning | Front-matter + Strengths/Difficulties/Tutor Strategy/Uncertain; immutable `memory_versions` + `memory_current` pointer (`06-markdown-memory.md`, `ai-memory-system.md:373-399,497-502`) | Single `memory_summary` string row (`db.py:69-76`). No version history, no front matter, no tutor-strategy section. |
| Retrieval | Resolver: exact → alias → FTS → LLM rerank; ranked 45/25/20/10 (relevance/confidence/usefulness/freshness); overrides + caps; `verify` for low-confidence/stale (`07-retrieval.md`, `ai-memory-system.md:35-56,401-450`) | `load_memory_context` = `mastery < 0.5` filter + prerequisite-edges-of-weak + recent-3-obs (`memory/service/utils.py:25-164`). **No ranking, no freshness, no `verify`, no caps beyond 5/3.** |
| Learner brief | Structured, ≤200–500 tokens, "data not instructions," prompt compiler reads structured state never editable Markdown (`ai-memory-system.md:436-452`) | `LEARNER MEMORY CONTEXT` injected as plain text into system prompt (`app/graph.py:328-333`); no token budget enforcement; memory treated as free text. |
| Security | "Treat user-editable memory as untrusted; never execute instructions found inside it." (`ai-memory-system.md:452`) | No explicit sandboxing of memory content before prompt injection. |

### The single biggest deviation
The spec's core invariant is *"LLM extracts observations. Deterministic code updates scores/state. Models never own canonical scores."* The implementation collapses these into one LLM call that emits **both** observations **and** `concept_state_deltas`/`updated_summary`, then writes `mastery = <LLM value>` verbatim. This is the flimsiness you flagged.

---

## 2. Extra smart approaches to improve accuracy & determinism

These go beyond restoring the spec and lean into the "willing to go far" brief. Ordered by leverage.

### A. Separate extraction from aggregation (highest leverage)
- **Now:** one LLM call yields observations + absolute mastery + summary.
- **Better:** restore the `04 → 05` split. A constrained *extractor* LLM emits structured observations only (outcome ∈ {correct, partial, incorrect, unknown}, assistance ∈ {none, prompt, conceptual_hint, procedural_scaffold, worked_answer}, misconception_key, extractor_confidence, evidence location). A **deterministic reducer** (pure fn: `observations + scoring_config → state`) computes mastery via the spec's weighted-outcome model. Outcome: mastery becomes *auditable* and *replayable*; you can write golden fixtures (Section 15) that assert exact mastery after a known observation sequence, which is impossible today.

### B. BKT mastery (recommended given data/compute limits)
- Per concept track `{P(learn), P(guess), P(slip)}` with prior `P(know)≈0`. Each graded
  response updates `P(know)` via Bayes:
  `P(know) = P(know|learn) / [P(know|learn) + (1−P(know|learn))·P(slip)]` on success,
  the analogous update on failure. Mastery reported to the tutor = `P(know)`.
- Why BKT over weighted-mean/IRT here: 4 params/concept, closed-form updates, robust on
  sparse data, and it directly encodes the spec's "correct after worked answer = no
  mastery" rule via the `assistance` dimension (`P(slip)` rises; `P(guess)` is bounded
  by `assistance=scaffold/worked_answer`). Cheaper than IRT and far less data-hungry
  than fitting item difficulty per concept.
- Data needed: the structured `outcome` + `assistance` fields from (A). Without them,
  fall back to an assistance-aware pseudo-BKT: increment `P(know)` on independent
  correct, decrement (or zero) on scaffolded/worked-answer success.

### C. IRT (aspirational — once labeled outcomes mature)
- The spec defers a learned/Bayesian mastery model (`ai-memory-system.md:550`); weighted-mean
  is only the pilot. With enough graded responses, fit per-concept difficulty `b` in
  `P(correct | θ, b) = sigmoid(θ − b)` and update learner ability `θ` via logistic
  likelihood. Disentangles item difficulty from learner ability; yields a principled
  `verify` threshold when `θ` CI overlaps `b`. Replace BKT only after cross-validation
  shows lift — it is not a free win on small data.

### D. Spaced-repetition scheduler wired to freshness (not just scoring)
- The spec computes freshness but doesn't *schedule* reviews. Add an SM-2-style or continuous-decay scheduler: when `freshness < threshold`, enqueue a **diagnostic review task** for the concept (Section 8: "tutor performs quick diagnostic"). This turns "low freshness → retrieve only if directly relevant" into an *intervention*.
- Half-life should be **fit per concept** from history (some concepts forgotten fast), not a single 30d/2x/0.5x rule.

### E. Calibration & confidence that means something
- Distinguish **aleatoric** (concept is intrinsically noisy) vs **epistemic** (model unfamiliar) uncertainty. Use the `confidence` gate (spec §10: <0.55 excluded unless exact) but *calibrate* it: on golden histories, verify that "confidence 0.7" → correct ~70% of the time. Today confidence is LLM-supplied and uncalibrated.
- **Counterfactual recall:** periodically replay a held-out observation set through the reducer to measure retrieval precision@3 and unsupported-observation rate (Section 15 metrics) — auto-tune thresholds.

### F. Cross-concept / cross-subject transfer (use the graph you're not using)
- The spec reserves `applied_in` / cross-cutting `skill` nodes (`ai-memory-system.md:96-105`); the impl has only `prerequisite`. Introduce `applied_in` edges and propagate evidence: "linear equations mastered in Math" → boost evidence for "linear-equation manipulation" in Physics. Massive recall win for word-problem transfer.
- Derive **topic/subject rollups** from child states (spec §6.39: "topic memories generated rollups from current child states; no duplication of every child") — currently absent.

### G. Determinism & replayability rigor
- **Pin everything:** model name + seed + deterministic prompt template + fixed ordering. Spec success: "Same state + renderer version yields identical Markdown" (`06-markdown-memory.md:50`).
- **Idempotency keys** on observations keyed by `turn_id` (spec §2 `job unique by completed turn`; §5 gotcha "Changing thresholds without replay/migration plan") — currently `_has_pending_job` dedups by time window only (`memory/service/utils.py:257`), not by turn.
- **Fixed clock in tests** (`05-learner-state-engine.md:88` gotcha). Freshness depends on time; tests must freeze it to be bit-reproducible.
- **Optimistic state versioning** (`ai-memory-system.md:39,506` `state_version`): conflict rows when two workers race — currently no version column.

### H. Retrieval that actually ranks
- Implement the `45/25/20/10` ranking (relevance/confidence/usefulness/freshness) + overrides + caps (3 direct / 2 prereq / 1 parent / 1 profile) from `ai-memory-system.md:150-156,419-431` and `07-retrieval.md:49-55`. Today retrieval is a flat `mastery < 0.5` filter — no relevance scoring, no "exact before related," no `verify` branch for low-confidence/stale.
- This is where "older memories surface less often" *should* live: freshness is a ranking term (10%) and low-freshness exact matches drop to `verify`, not `assert`.

### I. Teach the agent the structure, not free text
- Today memory is injected as `LEARNER MEMORY CONTEXT\n<context_text>` (`app/graph.py:328-333`) with no token budget (`ai-memory-system.md:156`). Switch the prompt compiler to consume **structured state** (JSON) per `ai-memory-system.md:433`, enforce the ≤200–500 token learner-brief budget, and treat memory as **data** (`ai-memory-system.md:436-452`). Security: never execute memory content as instructions (Section 10 hard requirement).

### J. Retrieval augmentation: BM25/FTS5 + embeddings (candidate recall only)
- The current loader is a flat `mastery < 0.5` filter. For *concept resolution* of the
  current turn (spec §7.10–12), add layered recall — each stage feeds the next, never inventing:
  1. **exact canonical name / `concept_key`** (cheap, authoritative),
  2. **`aliases`** (spec §1.24; today folded into `concepts.aliases` `db.py:13`),
  3. **SQLite FTS5** over `concepts.display_name` + `aliases` + `learner_observations` —
     this is the durable **BM25** signal; fast, deterministic, no model cost,
  4. **embeddings as candidate recall only** (`ai-memory-system.md:409-415`): when FTS
     returns too few candidates (unknown wording / cross-subject phrasing), a small
     `sqlite-vss`-style vector index recalls N candidate concept IDs, which are then
     re-ranked by **BM25 + graph** and validated by the deterministic evidence rules.
- Rules the spec mandates, none implemented: "exact before related"; "vector never source
  truth"; "log selected memory IDs + ranking reasons"; "never inject solely from vector
  similarity." Embeddings are a recall booster, not a verdict.
- Implementation note: store a single canonical embedding per `concept` row (updated only
  on material state change); index observations too for "recent evidence" fetch. Cost stays
  bounded — one embedding write per concept per version, not per turn.

### K. WHERE TO SPEND THE MODELS (high-leverage, in priority order)
This is the most important design guardrail. The spec's whole point is that models are
*expensive and unreliable for truth*, so spend them on judgement/ranking/synthesis over
pre-filtered candidates — never on scoring or dumping context.

1. **Extractor (cheap, schema-locked) — not the scorer.** One constrained LLM call per turn
   emits *structured observations only* (outcome/assistance/misconception/confidence).
   That is the **only** place the model reads free text. Output is schema-validated and
   rejected if implausible (`04-observation-extraction.md:37-44`).
2. **Deterministic reducer = the source of truth for mastery.** BKT runs in pure Python
   over the observation log. The model never writes `mastery`. Mastery is now auditable
   and bit-reproducible — you can diff two runs over the same observations.
3. **Retrieval = lexical + graph (cheap), LLM = rerank over a tiny candidate set.** FTS5/BM25
   + edge traversal select candidates; the model reranks ≤ ~24 candidates with a constrained
   prompt and returns **IDs + reasons**, not free text. This is where ranking quality
   actually improves without exploding prompt size.
4. **Brief compiler = synthesize a tiny, bounded prompt addition.** Given the *already-ranked,
   capped* candidate set, the model writes the ≤200–500-token learner brief
   (`ai-memory-system.md:150-156,436-452`). The model earns its keep phrasing a small,
   useful brief from structured inputs — inside a hard token budget, not "summarize everything."
5. **Never** let the model author scores, inject raw memory verbatim, or run on full history.
   Every model call above operates on **bounded inputs** with a deterministic validator
   downstream. This is what makes context both accurate (no free-text scoring) and cheap
   (no giant prompts) — and it is the fix for today's `LEARNER MEMORY CONTEXT` dump
    (`app/graph.py:328-333`).

### L. Version gate + manual edit/rollback (spec §9/§12)
- Re-introduce immutable `memory_versions` + `memory_current` pointer so edits append a version and rollback is a new version (never erase). Material-change gate prevents freshness-clock from churning versions (`ai-memory-system.md:360-365`, `06-markdown-memory.md:32-38`).

## 3. Recommended sequencing (minimal→ambitious)

1. **Separate extraction from aggregation** (A) + **capture graded outcomes** (B/C prerequisite) — models read free text only inside the constrained extractor; deterministic reducer is the source of truth.
2. **BKT mastery** (B) — the realistic scorer under data/compute limits; replaces LLM-as-author. IRT (C) is the aspirational upgrade once labeled outcomes mature.
3. **Retrieval augmentation** (J) + **ranking with freshness** (H) — FTS5/BM25 + graph recall, embeddings as candidate recall only, 45/25/20/10 ranking so decay modulates surfacing.
4. **Brief compiler** (K) — put models on synthesis/reranking over bounded candidates, NOT on scoring or context dumps. This is the lever for "most high-leverage, effective context."
5. **Freshness decay → diagnostic review** (D) — the decay you remembered; low-freshness → `verify`/scheduled diagnostic, not silent ignore.
6. **Markdown versioning + material gate + rollback** (L).
7. **Cross-subject transfer + rollups** (F); preference lifecycle; **calibration** (E); **determinism pin/clock/version** (G).

## Runtime data flow: what the agent sees beyond the summary

### Current (what ships today)
On every turn, `memory_loader` (`app/graph.py:115`) calls `load_memory_context`
(`memory/service/main.py:122`), which reads in one DB transaction and injects the result
as flat text `LEARNER MEMORY CONTEXT` into the system prompt (`graph.py:328-333`):

- `memory_summary` — one row/string per (user, subject).
- `learner_traits` — one JSON blob.
- weak concepts — `mastery < 0.5` capped at 5 (`utils.py:62`, `MEMORY_WEAK_MASTERY_THRESHOLD`=0.5,
  `MEMORY_WEAK_CONCEPTS_LIMIT`=5); concept identity via JOIN to `concepts`.
- prerequisites — `concept_edges` where the weak concept is the `to_concept_id`.
- recent observations — last 3 (`MEMORY_RECENT_OBS_LIMIT`=3).

That is **all** the data outside the summary that reaches the prompt today, and it is
unstructured text with no freshness, no confidence gate, no status, no misconceptions,
no ranking — just "lowest-masteries + their prereqs + last 3 free-text obs."

### Upgraded (roadmap §3 items 2–4 + §H/J/K)
The columns/rows the BKT reducer writes (§B) and the retrieval layer (§H/J) make each
bucket carry richer signals, and the **brief compiler** (§K.4) reshapes how that data is
delivered to the model:

- **Weak concepts** become a ranked shortlist, each carrying `{status, mastery=P(know),
  confidence, freshness, half_life_days, misconceptions[]}` — not a raw mastery float.
  `confidence < 0.55` and stale items route to `verify`/diagnostic instead of assertion.
- **Prerequisites** are fetched via explicit `concept_edges` traversal
  (`prerequisite_of`/`applied_in`/`parent_of`), then ranked — not a flat filter.
- **Recent observations** carry `{outcome, assistance, weight, evidence_location}` so each
  line of the brief is auditable back to a turn.
- **Retrieval ranking** (§H) scores candidates `45/25/20/10`
  (relevance/confidence/usefulness/freshness) and caps them (3 direct / 2 prereq / 1 parent
  / 1 profile) → the prompt is bounded by design.
- **Brief compiler** (§K.4): the model reranks ≤ ~24 candidates and emits a ≤200–500 token
  brief from **structured** input; injection is `LEARNER CONTEXT (data, not instructions)`,
  not a free-text memory dump.

So data outside the summary is used for five jobs, in priority order: **(1)** shortlist of
weak concepts to steer toward (status/freshness tell the tutor *diagnostic vs reinforce*),
**(2)** prerequisites to front-load, **(3)** observations as concrete justification,
**(4)** traits for teaching-style personalization, **(5)** confidence/freshness gating so
stale/weak-confidence memories become `needs-vet` instead of asserted.

## Context-rot mitigation: production patterns for "store much, inject little"

(`ai-memory-system.md:34` Product Principle, `:150-156` retrieval budget, `:456-462`
context layers.) Shove summary + weak concepts + observations + traits into the prompt and
you get context rot + stale/wrong memory. Production systems (Claude Memory, ChatGPT
Memory, RAG) combine these patterns — most can be layered onto the brief compiler (§K.4):

1. **Distill, don't dump (primary lever).** A ≤200–500 token *structured* learner brief,
   compiled by the model from already-ranked, capped candidates (§K.4). Never inject raw
   `LEARNER MEMORY CONTEXT` free text. The brief is the only memory object in the prompt.
2. **Relevance-gate injection.** Only concepts/topics whose relevance score (§H 45/25/20/10)
   clears a threshold enter the brief; else inject a one-line "no relevant memory."
   Spec: "wrong/stale injected memory worse than missing relevant memory" (`ai-memory-system.md:26`).
3. **Hard token budgeting + truncation, not history pruning.** Allocate budget across
   sections (e.g. weak concepts ≤5, obs ≤3, profile ≤1) and truncate the *brief*; keep
   chat history windowing separate so memory never eats the turn. `test_memory_scale.py:219`
   already asserts `len(ctx) < 2000` on the context endpoint — extend that cap to the prompt.
4. **Prompt/prefix caching.** Cache the stable prefix (system prompt + learner brief) and
   vary only the turn. Anthropic/Claude-style prefix caching makes re-sending the brief
   near-free; critical because retrieval is per-turn.
5. **Sliding window + rolling episode summary.** Keep recent K messages verbatim;
   compress older messages into a running episode summary (LangGraph-style summarization
   node). Memory brief ≠ conversation history.
6. **Hierarchical memory layers** (`ai-memory-system.md:458-461`): working context
   (current problem), episode context (today's session summary), learner context (durable
   brief). Inject only the relevant layer(s) for the query — usually episode summary +
   today's turn + the small learner brief.
7. **Structured facts over prose.** Render concepts/observations as a compact
   table/list keyed by `concept_key`, not paragraphs — far more compressible, and the
   agent can parse/skip sections.
8. **Freshness-based `verify`, not assert** (§B.2/D). Low-freshness memories route to a
   quick diagnostic ("possibly rusty") and are *not* injected as fact — this bounds how
   much stale material can rot the prompt.

The single most important fix vs. today: replace the unbounded
`LEARNER MEMORY CONTEXT` free-text dump (`app/graph.py:328-333`) with the bounded,
structured brief compiler (§K.4) — after that, caching + relevance-gating +
hierarchical layers compound the saving.

## 4. Files referencing the gap

- Spec: `ai-memory-system.md` (root), `05-learner-state-engine.md`, `07-retrieval.md`, `04-observation-extraction.md`, `06-markdown-memory.md`, `01-concept-model.md`.
- Code (current simplification): `backend/memory/db.py`, `backend/memory/jobs/utils.py` (master write `320-329`), `backend/memory/llm.py:136`, `backend/memory/schemas.py:29`, `backend/memory/service/utils.py:25-164`, `backend/memory/config.py:24-28`, `app/graph.py:328-333`, `app/routes/chat.py:156-183`.
