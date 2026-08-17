-- Reset the memory DB schema, then seed starter data.
-- Mirrors data/purge-and-seed.sql: DROP → CREATE → INSERT.

DROP TABLE IF EXISTS concept_edges;
DROP TABLE IF EXISTS learner_concept_state;
DROP TABLE IF EXISTS learner_observations;
DROP TABLE IF EXISTS learner_traits;
DROP TABLE IF EXISTS memory_summary;
DROP TABLE IF EXISTS memory_update_jobs;
DROP TABLE IF EXISTS retrieval_traces;
DROP TABLE IF EXISTS concepts;

CREATE TABLE concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    concept_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(subject_id, concept_key)
);

CREATE INDEX idx_concepts_subject ON concepts (subject_id);

CREATE TABLE concept_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_concept_id INTEGER NOT NULL,
    to_concept_id INTEGER NOT NULL,
    relation TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(from_concept_id, to_concept_id, relation),
    FOREIGN KEY (from_concept_id) REFERENCES concepts(id),
    FOREIGN KEY (to_concept_id) REFERENCES concepts(id)
);

CREATE INDEX idx_edges_from ON concept_edges (from_concept_id);
CREATE INDEX idx_edges_to ON concept_edges (to_concept_id);

CREATE TABLE learner_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    observation TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_observations_scope_time ON learner_observations (user_id, subject_id, created_at DESC);

CREATE TABLE learner_concept_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    concept_id INTEGER NOT NULL,
    mastery REAL NOT NULL DEFAULT 0.0,
    confidence REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, subject_id, concept_id),
    FOREIGN KEY (concept_id) REFERENCES concepts(id)
);

CREATE INDEX idx_concept_state_scope ON learner_concept_state (user_id, subject_id, mastery);

CREATE TABLE learner_traits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    traits_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, subject_id)
);

CREATE TABLE memory_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, subject_id)
);

CREATE TABLE memory_update_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    chat_id INTEGER,
    trace_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_jobs_status_time ON memory_update_jobs (status, created_at);
CREATE INDEX idx_jobs_scope_time ON memory_update_jobs (user_id, subject_id, created_at DESC);

CREATE TABLE retrieval_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    query_text TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_traces_scope_time ON retrieval_traces (user_id, subject_id, created_at DESC);

-- =====================================================================
-- User 1 (alice@school.edu) — subject 1 (AP Calculus BC)
-- =====================================================================

INSERT INTO concepts (subject_id, concept_key, display_name, aliases)
VALUES
    (1, 'quadratic_formula', 'Quadratic Formula', '["quadratic equation formula"]'),
    (1, 'completing_the_square', 'Completing the Square', '[]');

INSERT INTO concept_edges (from_concept_id, to_concept_id, relation, weight)
SELECT c1.id, c2.id, 'related', 0.8
FROM concepts c1
JOIN concepts c2
  ON c1.concept_key = 'completing_the_square'
 AND c1.subject_id = 1
 AND c2.concept_key = 'quadratic_formula'
 AND c2.subject_id = 1;

INSERT INTO learner_observations (user_id, subject_id, observation, source)
VALUES (1, 1, 'Needs reminders to track signs in b^2 - 4ac.', 'seed');

INSERT INTO learner_traits (user_id, subject_id, traits_json)
VALUES (1, 1, '{"prefers_step_by_step": true}');

INSERT INTO memory_summary (user_id, subject_id, summary)
VALUES (
  1,
  1,
  'Recent learner observations:\n- Needs reminders to track signs in b^2 - 4ac.'
);

INSERT INTO memory_update_jobs (user_id, subject_id, chat_id, status, payload_json, updated_at)
VALUES (1, 1, NULL, 'pending', '{"trigger":"seed","messages":[{"role":"user","content":"I keep forgetting the minus sign"}] }', datetime('now'));

INSERT INTO retrieval_traces (user_id, subject_id, query_text, result_json)
VALUES (1, 1, 'quadratic formula sign mistake', '{"hits":["quadratic_formula"]}');

-- =====================================================================
-- User 3 (leeyihong03@gmail.com) — AP Biology (subject 4), AP Calculus AB (subject 6)
-- User 4 (leeshihau@gmail.com) — AP Biology (subject 8), AP Calculus AB (subject 10)
-- =====================================================================

INSERT INTO concepts (subject_id, concept_key, display_name, aliases)
VALUES
    (4, 'mitosis', 'Mitosis', '["cell division stages"]'),
    (4, 'meiosis', 'Meiosis', '["gamete division"]'),
    (6, 'limits_continuity', 'Limits and Continuity', '["epsilon delta"]'),
    (6, 'derivatives', 'Derivatives', '["differentiation"]'),
    (8, 'mitosis', 'Mitosis', '["cell division stages"]'),
    (8, 'meiosis', 'Meiosis', '["gamete division"]'),
    (10, 'limits_continuity', 'Limits and Continuity', '["epsilon delta"]'),
    (10, 'derivatives', 'Derivatives', '["differentiation"]');

INSERT INTO concept_edges (from_concept_id, to_concept_id, relation, weight)
SELECT c1.id, c2.id, 'related', 0.8
FROM concepts c1
JOIN concepts c2
  ON c1.concept_key = 'meiosis'
 AND c1.subject_id IN (4, 8)
 AND c2.concept_key = 'mitosis'
 AND c2.subject_id = c1.subject_id;

INSERT INTO concept_edges (from_concept_id, to_concept_id, relation, weight)
SELECT c1.id, c2.id, 'related', 0.8
FROM concepts c1
JOIN concepts c2
  ON c1.concept_key = 'derivatives'
 AND c1.subject_id IN (6, 10)
 AND c2.concept_key = 'limits_continuity'
 AND c2.subject_id = c1.subject_id;

INSERT INTO learner_observations (user_id, subject_id, observation, source)
VALUES
    (3, 4, 'Confuses meiosis I and meiosis II; solid on mitosis stage order.', 'seed'),
    (4, 8, 'Mixes up crossing over location; strong recall of mitosis phases.', 'seed');

INSERT INTO learner_traits (user_id, subject_id, traits_json)
VALUES
    (3, 4, '{"prefers_visual_diagrams": true, "wants_exam_tips": true}'),
    (4, 8, '{"prefers_visual_diagrams": true}');

INSERT INTO memory_summary (user_id, subject_id, summary)
VALUES
    (3, 4, 'Recent learner observations:\n- Confuses meiosis I and meiosis II; solid on mitosis stage order.'),
    (4, 8, 'Recent learner observations:\n- Mixes up crossing over location; strong recall of mitosis phases.');

INSERT INTO memory_update_jobs (user_id, subject_id, chat_id, status, payload_json, updated_at)
VALUES
    (3, 4, NULL, 'pending', '{"trigger":"seed","messages":[{"role":"user","content":"Meiosis keeps confusing me"}] }', datetime('now')),
    (4, 8, NULL, 'pending', '{"trigger":"seed","messages":[{"role":"user","content":"Where does crossing over happen again?"}] }', datetime('now'));

INSERT INTO retrieval_traces (user_id, subject_id, query_text, result_json)
VALUES
    (3, 4, 'meiosis vs mitosis confusion', '{"hits":["meiosis","mitosis"]}'),
    (4, 8, 'crossing over prophase I', '{"hits":["meiosis"]}');