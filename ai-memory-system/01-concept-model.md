# Task 01

## 1. Name

Concept Model and Pilot Ontology

## 2. Purpose in Bigger Picture

Give every subject/topic/concept stable identity. Enables evidence attachment, prerequisite lookup, cross-subject transfer, retrieval. Avoid memories keyed by inconsistent free-text names.

## 3. Detailed Implementation Idea

Define node types:

- `subject`
- `topic`
- `concept`
- `skill`: cross-cutting behavior; e.g. interpreting word problems

Define relations:

- `parent_of`
- `prerequisite_of`
- `related_to`
- `applied_in`

Each node:

```text
stable ID
canonical name
short description
aliases
node type
status: proposed | active | retired
```

Add curriculum mapping separately. Canonical concept can appear in multiple syllabuses/topics.

Pilot: manually seed 1–2 target syllabuses. Enough detail to distinguish teachable concepts; avoid universal ontology.

Unknown concept workflow:

```text
resolve alias/candidates
-> unresolved record
-> DeepSeek may propose node/relations
-> validate duplicates/cycles
-> activate
```

SQLite:

- `concepts`
- `concept_aliases`
- `concept_edges`
- optional `curriculum_concepts`

## 4. Success Criteria

- Stable concept ID remains after rename.
- One concept supports multiple parents/applications.
- Alias resolves to correct canonical ID.
- Cross-cutting skill can link across subjects.
- Unknown phrase does not automatically create active concept.
- Parent/prerequisite cycles rejected.
- Seed syllabus can represent test homework examples without forced duplicate nodes.
- Given same seeded data + query, deterministic lookup returns same candidate set.

## 5. Gotchas

- Concepts too broad: memory vague.
- Concepts too narrow: retrieval fragmentation.
- Same name, different meaning across subjects.
- Treating hierarchy as strict tree.
- LLM inventing duplicate nodes.
- Renaming IDs; IDs must be opaque/stable.
- Retiring concept must not orphan historical observations.

## 6. Related Concepts / Tasks

- Task 02 stores graph.
- Task 04 observations require concept IDs.
- Task 07 resolves queries and traverses relations.
- Task 06 parent memories derive from graph.
- Keep relation types extensible; do not build generic graph framework beyond named relations.
