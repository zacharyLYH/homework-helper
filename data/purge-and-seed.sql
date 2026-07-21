DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS chats;
DROP TABLE IF EXISTS subjects;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS verification_codes;
DELETE FROM sqlite_sequence;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('guide', 'just-solve')),
    title TEXT NOT NULL DEFAULT 'New Chat',
    total_tokens INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (subject_id) REFERENCES subjects(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    image_base64 TEXT,
    image_media_type TEXT,
    metadata_json TEXT,
    token_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE verification_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    code TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO users (email) VALUES ('alice@school.edu');
INSERT INTO users (email) VALUES ('bob@school.edu');
INSERT INTO users (email) VALUES ('leeyihong03@gmail.com');

INSERT INTO subjects (user_id, name) VALUES (1, 'AP Calculus BC');
INSERT INTO subjects (user_id, name) VALUES (1, 'Physics C');
INSERT INTO subjects (user_id, name) VALUES (2, 'Organic Chemistry');

INSERT INTO chats (subject_id, user_id, mode, title, input_tokens, output_tokens, total_tokens) VALUES (1, 1, 'guide', 'Derivatives help', 130, 105, 235);
INSERT INTO chats (subject_id, user_id, mode, title, input_tokens, output_tokens, total_tokens) VALUES (1, 1, 'just-solve', 'Integration by parts', 60, 70, 130);
INSERT INTO chats (subject_id, user_id, mode, title, input_tokens, output_tokens, total_tokens) VALUES (2, 1, 'guide', 'Kinematics', 55, 50, 105);
INSERT INTO chats (subject_id, user_id, mode, title, input_tokens, output_tokens, total_tokens) VALUES (3, 2, 'just-solve', 'SN1 vs SN2', 45, 65, 110);

INSERT INTO messages (chat_id, role, content, metadata_json, token_count) VALUES
(1, 'user', 'What is the chain rule?', NULL, 0),
(1, 'assistant', 'The chain rule: d/dx[f(g(x))] = f''(g(x)) * g''(x).', '{"node":"math","token_usage":{"input_tokens":50,"output_tokens":60,"total_tokens":110}}', 110),
(1, 'user', 'Can you give me an example?', NULL, 0),
(1, 'assistant', 'If y = sin(x²), then dy/dx = cos(x²) * 2x.', '{"node":"math","token_usage":{"input_tokens":80,"output_tokens":45,"total_tokens":125}}', 125),
(2, 'user', 'Evaluate integral of x*e^x', NULL, 0),
(2, 'assistant', '∫x*e^x dx = e^x(x-1) + C', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"1"}}],"token_usage":{"input_tokens":60,"output_tokens":70,"total_tokens":130}}', 130),
(3, 'user', 'Car accelerates from rest at 2m/s². Position at t=5s?', NULL, 0),
(3, 'assistant', 'x = ½at² = ½ * 2 * 25 = 25 meters', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"0.5 * 2 * 25"}}],"token_usage":{"input_tokens":55,"output_tokens":50,"total_tokens":105}}', 105),
(4, 'user', 'Difference between SN1 and SN2?', NULL, 0),
(4, 'assistant', 'SN1: two-step, carbocation, racemization, tertiary. SN2: one-step, backside attack, inversion, primary.', '{"node":"general","token_usage":{"input_tokens":45,"output_tokens":65,"total_tokens":110}}', 110);

INSERT INTO subjects (user_id, name) VALUES (3, 'AP Biology');
INSERT INTO subjects (user_id, name) VALUES (3, 'US History');

INSERT INTO chats (subject_id, user_id, mode, title, input_tokens, output_tokens, total_tokens) VALUES (4, 3, 'guide', 'Cell division', 70, 80, 150);
INSERT INTO chats (subject_id, user_id, mode, title, input_tokens, output_tokens, total_tokens) VALUES (4, 3, 'just-solve', 'Meiosis vs Mitosis', 60, 90, 150);
INSERT INTO chats (subject_id, user_id, mode, title, input_tokens, output_tokens, total_tokens) VALUES (5, 3, 'guide', 'Civil War causes', 120, 160, 280);

INSERT INTO messages (chat_id, role, content, metadata_json, token_count) VALUES
(5, 'user', 'Explain the stages of mitosis', NULL, 0),
(5, 'assistant', 'Mitosis: Prophase, Metaphase, Anaphase, Telophase. Chromosomes condense, align, separate, and reform nuclei.', '{"node":"biology","token_usage":{"input_tokens":70,"output_tokens":80,"total_tokens":150}}', 150),
(6, 'user', 'Difference between meiosis and mitosis?', NULL, 0),
(6, 'assistant', 'Mitosis: 1 division, 2 diploid cells, identical. Meiosis: 2 divisions, 4 haploid cells, genetic variation via crossing over.', '{"node":"biology","token_usage":{"input_tokens":60,"output_tokens":90,"total_tokens":150}}', 150),
(7, 'user', 'What caused the Civil War?', NULL, 0),
(7, 'assistant', 'Primary causes: slavery expansion, states rights disputes, economic differences between industrial North and agricultural South.', '{"node":"history","token_usage":{"input_tokens":55,"output_tokens":85,"total_tokens":140}}', 140),
(7, 'user', 'What was the Emancipation Proclamation?', NULL, 0),
(7, 'assistant', 'Issued by Lincoln in 1863, it declared slaves in Confederate states free. It changed the war focus to include ending slavery.', '{"node":"history","token_usage":{"input_tokens":65,"output_tokens":75,"total_tokens":140}}', 140);
