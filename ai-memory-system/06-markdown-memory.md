# Task 06

## 1. Name

Markdown Memory Rendering and Versioning

## 2. Purpose in Bigger Picture

Create readable/debuggable memory artifacts without making free-form prose canonical. Minimize rewrites/context rot.

## 3. Detailed Implementation Idea

Render structured state into stable Markdown template:

```text
front matter: scope, concept ID, scores, status, version
strengths
difficulties/misconceptions
tutor strategy
uncertain/stale claims
```

Version only material changes:

- status changed after hysteresis
- misconception added/resolved
- independence category changed
- stable preference changed
- tutor strategy changed
- manual edit/rollback

No version for:

- small score movement
- ordinary question
- unsupported inference
- clock-only freshness movement

Concept memories primary. Topic/subject memories generated rollups from current child states; concise patterns only, no duplication of every child.

Prefer deterministic templates. If DeepSeek writes optional prose, constrain sections/length and validate facts against state.

SQLite:

- immutable `memory_versions`
- `memory_current` pointer
- material-change reason
- renderer/config version

## 4. Success Criteria

- Same state + renderer version yields identical Markdown.
- Non-material score update creates no version.
- Material status/misconception change creates one version.
- Version reason identifies triggering change.
- Parent rollup refreshes after relevant child change.
- Rollup never contradicts current child states.
- Markdown stays within configured size.
- Optional model prose cannot invent state/facts.
- Current pointer updates atomically with new version.

## 5. Gotchas

- LLM rewording creates noisy versions.
- Subject/topic rollups becoming huge.
- Independent parent truth drifting from children.
- Raw user-edited Markdown injected as instructions.
- Freshness clock creating daily versions.
- Concurrent children producing stale rollup.
- Losing renderer version needed for replay.

## 6. Related Concepts / Tasks

- Task 05 supplies canonical state/material diff.
- Task 02 stores versions/pointers.
- Task 07 retrieves current memories/state.
- Task 09 exposes diff/edit/rollback.
- Task 10 checks deterministic output.
- Prompt compiler should read structured state; Markdown mainly visibility/export.
