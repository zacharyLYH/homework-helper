"""Prompt templates for the memory LLM evaluation worker."""

from __future__ import annotations

import json

from memory.schemas import MemoryEvaluationInput

SYSTEM_PROMPT = (
    "You are a memory curator for a homework tutor. "
    "Respond with a fast, surface-level scan of the turn — do NOT reason deeply or explain your thinking. "
    "Update memory sparingly. Only surface signals with concrete evidence. "
    "Return JSON immediately without preamble."
)

_SCHEMA_HINT = """\
Return JSON matching this schema exactly:
{
  "skip": bool,
  "observations": [str, ...],
  "concept_upserts": [{"concept_key": str, "display_name": str, "aliases": [str]}],
  "concept_edges": [{"from_concept_key": str, "to_concept_key": str, "relation": "prerequisite"|"related", "weight": float}],
  "concept_state_deltas": [{"concept_key": str, "mastery": float, "confidence": float}],
  "trait_updates": {str: str},
  "updated_summary": str
}"""


def render_user_prompt(*, current_state: MemoryEvaluationInput) -> str:
    weak = (
        ", ".join(f"{name} ({mastery:.2f})" for name, mastery in current_state.current_weak_concepts)
        or "none"
    )
    traits = (
        json.dumps(current_state.current_traits, ensure_ascii=False)
        if current_state.current_traits
        else "{}"
    )
    turn = json.dumps(current_state.turn_snippet, ensure_ascii=False)

    return f"""\
CURRENT MEMORY STATE:
Summary: {current_state.current_summary or "(empty)"}
Traits: {traits}
Weak concepts: {weak}

LATEST TURN:
{turn}

INSTRUCTIONS:
- If nothing concrete is learned about the student, return {{"skip": true}}.
- Extract new observations only if they contain specific evidence about understanding, mistakes, or preferences.
- Only upsert concepts explicitly discussed.
- Only propose edges when the relationship is clearly demonstrated in the turn.
- Mastery: 0.0=no evidence, 0.5=partial, 1.0=solid demonstration.
- Confidence: how sure YOU are of the mastery estimate.
- Traits: extract stable preferences (e.g., "prefers_visuals": "true") — do not invent.
- Concept keys: use snake_case, ASCII lowercase (they will be normalized regardless).
- Updated summary: concise (max 300 chars), replaces old summary. Empty string if skip=true.

{_SCHEMA_HINT}"""
