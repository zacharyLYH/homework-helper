INSERT OR IGNORE INTO concepts (subject_id, concept_key, display_name, aliases)
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
 AND c2.subject_id = 1
WHERE NOT EXISTS (
  SELECT 1
  FROM concept_edges ce
  WHERE ce.from_concept_id = c1.id
    AND ce.to_concept_id = c2.id
    AND ce.relation = 'related'
);

INSERT INTO learner_observations (user_id, subject_id, observation, source)
SELECT 1, 1, 'Needs reminders to track signs in b^2 - 4ac.', 'seed'
WHERE NOT EXISTS (
  SELECT 1
  FROM learner_observations
  WHERE user_id = 1
    AND subject_id = 1
    AND observation = 'Needs reminders to track signs in b^2 - 4ac.'
);

INSERT OR IGNORE INTO learner_traits (user_id, subject_id, traits_json)
VALUES (1, 1, '{"prefers_step_by_step": true}');

INSERT OR IGNORE INTO memory_summary (user_id, subject_id, summary)
VALUES (
  1,
  1,
  'Recent learner observations:\n- Needs reminders to track signs in b^2 - 4ac.'
);

INSERT INTO memory_update_jobs (user_id, subject_id, chat_id, status, payload_json, updated_at)
SELECT
  1,
  1,
  NULL,
  'pending',
  '{"trigger":"seed","messages":[{"role":"user","content":"I keep forgetting the minus sign"}] }',
  datetime('now')
WHERE NOT EXISTS (
  SELECT 1
  FROM memory_update_jobs
  WHERE user_id = 1
    AND subject_id = 1
    AND status = 'pending'
);

INSERT INTO retrieval_traces (user_id, subject_id, query_text, result_json)
SELECT 1, 1, 'quadratic formula sign mistake', '{"hits":["quadratic_formula"]}'
WHERE NOT EXISTS (
  SELECT 1
  FROM retrieval_traces
  WHERE user_id = 1
    AND subject_id = 1
    AND query_text = 'quadratic formula sign mistake'
);
