DELETE FROM messages;
DELETE FROM chats;
DELETE FROM subjects;
DELETE FROM users;
DELETE FROM sqlite_sequence;

INSERT INTO users (email) VALUES ('alice@school.edu');
INSERT INTO users (email) VALUES ('bob@school.edu');

INSERT INTO subjects (user_id, name) VALUES (1, 'AP Calculus BC');
INSERT INTO subjects (user_id, name) VALUES (1, 'Physics C');
INSERT INTO subjects (user_id, name) VALUES (2, 'Organic Chemistry');

INSERT INTO chats (subject_id, user_id, mode, title) VALUES (1, 1, 'guide', 'Derivatives help');
INSERT INTO chats (subject_id, user_id, mode, title) VALUES (1, 1, 'just-solve', 'Integration by parts');
INSERT INTO chats (subject_id, user_id, mode, title) VALUES (2, 1, 'guide', 'Kinematics');
INSERT INTO chats (subject_id, user_id, mode, title) VALUES (3, 2, 'just-solve', 'SN1 vs SN2');

INSERT INTO messages (chat_id, role, content, metadata_json) VALUES
(1, 'user', 'What is the chain rule?', NULL),
(1, 'assistant', 'The chain rule: d/dx[f(g(x))] = f''(g(x)) * g''(x).', '{"node":"math","token_usage":{"input_tokens":50,"output_tokens":60,"total_tokens":110}}'),
(1, 'user', 'Can you give me an example?', NULL),
(1, 'assistant', 'If y = sin(x²), then dy/dx = cos(x²) * 2x.', '{"node":"math","token_usage":{"input_tokens":80,"output_tokens":45,"total_tokens":125}}'),
(2, 'user', 'Evaluate integral of x*e^x', NULL),
(2, 'assistant', '∫x*e^x dx = e^x(x-1) + C', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"1"}}],"token_usage":{"input_tokens":60,"output_tokens":70,"total_tokens":130}}'),
(3, 'user', 'Car accelerates from rest at 2m/s². Position at t=5s?', NULL),
(3, 'assistant', 'x = ½at² = ½ * 2 * 25 = 25 meters', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"0.5 * 2 * 25"}}],"token_usage":{"input_tokens":55,"output_tokens":50,"total_tokens":105}}'),
(4, 'user', 'Difference between SN1 and SN2?', NULL),
(4, 'assistant', 'SN1: two-step, carbocation, racemization, tertiary. SN2: one-step, backside attack, inversion, primary.', '{"node":"general","token_usage":{"input_tokens":45,"output_tokens":65,"total_tokens":110}}');