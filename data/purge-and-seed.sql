DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS chats;
DROP TABLE IF EXISTS subjects;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS verification_codes;
DELETE FROM sqlite_sequence;

ATTACH DATABASE 'data/debug.db' AS debug;
DELETE FROM debug.structured_logs;
DETACH DATABASE debug;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    refresh_token_expires_at TEXT,
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
    quote TEXT,
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

INSERT INTO users (email, refresh_token_expires_at) VALUES ('alice@school.edu', datetime('now', '+6 months'));
INSERT INTO users (email, refresh_token_expires_at) VALUES ('bob@school.edu', datetime('now', '+6 months'));
INSERT INTO users (email, refresh_token_expires_at) VALUES ('leeyihong03@gmail.com', datetime('now', '+6 months'));
INSERT INTO users (email, refresh_token_expires_at) VALUES ('leeshihau@gmail.com', datetime('now', '+6 months'));

INSERT INTO subjects (user_id, name) VALUES (1, 'AP Calculus BC');
INSERT INTO subjects (user_id, name) VALUES (1, 'Physics C');
INSERT INTO subjects (user_id, name) VALUES (2, 'Organic Chemistry');

INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (1, 1, 'Derivatives help', 130, 105, 235);
INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (1, 1, 'Integration by parts', 60, 70, 130);
INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (2, 1, 'Kinematics', 55, 50, 105);
INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (3, 2, 'SN1 vs SN2', 45, 65, 110);

INSERT INTO messages (chat_id, role, content, metadata_json, token_count, quote) VALUES
(1, 'user', 'What is the chain rule?', NULL, 0, NULL),
(1, 'assistant', 'The chain rule: d/dx[f(g(x))] = f''(g(x)) * g''(x).', '{"node":"math","tool_calls":[{"name":"web_search","args":{"query":"chain rule formula"},"id":"seed_call_1"},{"name":"calculator","args":{"expression":"d/dx sin(x^2)"},"id":"seed_call_2"}],"token_usage":{"input_tokens":50,"output_tokens":60,"total_tokens":110}}', 110, NULL),
(1, 'user', 'Can you give me an example?', NULL, 0, 'd/dx[f(g(x))] = f''(g(x)) * g''(x)'),
(1, 'assistant', 'If y = sin(x²), then dy/dx = cos(x²) * 2x.', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"d/dx sin(x^2)"},"id":"seed_call_3"}],"token_usage":{"input_tokens":80,"output_tokens":45,"total_tokens":125}}', 125, NULL),
(2, 'user', 'Evaluate integral of x*e^x', NULL, 0, NULL),
(2, 'assistant', '∫x*e^x dx = e^x(x-1) + C', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"integral x*e^x"},"id":"seed_call_4"}],"token_usage":{"input_tokens":60,"output_tokens":70,"total_tokens":130}}', 130, NULL),
(3, 'user', 'Car accelerates from rest at 2m/s². Position at t=5s?', NULL, 0, NULL),
(3, 'assistant', 'x = ½at² = ½ * 2 * 25 = 25 meters', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"0.5 * 2 * 25"},"id":"seed_call_5"}],"token_usage":{"input_tokens":55,"output_tokens":50,"total_tokens":105}}', 105, NULL),
(4, 'user', 'Difference between SN1 and SN2?', NULL, 0, NULL),
(4, 'assistant', 'SN1: two-step, carbocation, racemization, tertiary. SN2: one-step, backside attack, inversion, primary.', '{"node":"general","token_usage":{"input_tokens":45,"output_tokens":65,"total_tokens":110}}', 110, NULL);

INSERT INTO subjects (user_id, name) VALUES (3, 'AP Biology');
INSERT INTO subjects (user_id, name) VALUES (3, 'US History');
INSERT INTO subjects (user_id, name) VALUES (3, 'AP Calculus AB');
INSERT INTO subjects (user_id, name) VALUES (3, 'Computer Science');

INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (4, 3, 'Cell division', 210, 280, 490);
INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (4, 3, 'Meiosis vs Mitosis', 60, 90, 150);
INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (5, 3, 'Civil War causes', 180, 260, 440);
INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (5, 3, 'Reconstruction', 90, 130, 220);
INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (6, 3, 'Limits & continuity', 130, 190, 320);
INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (6, 3, 'Derivative practice', 100, 140, 240);
INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (7, 3, 'Binary trees', 160, 230, 390);
INSERT INTO chats (subject_id, user_id, title, input_tokens, output_tokens, total_tokens) VALUES (7, 3, 'Sorting algorithms', 90, 120, 210);

INSERT INTO messages (chat_id, role, content, metadata_json, token_count, quote) VALUES
-- Chat 5: Cell division (AP Biology, guide)
(5, 'user', 'Explain the stages of mitosis', NULL, 0, NULL),
(5, 'assistant', 'Mitosis has **4 main stages**:\n\n1. **Prophase** — Chromosomes condense, nuclear envelope breaks down.\n2. **Metaphase** — Chromosomes align at the metaphase plate.\n3. **Anaphase** — Sister chromatids separate and move to opposite poles.\n4. **Telophase** — Nuclear membranes reform, chromosomes decondense.\n\n$$\\text{Mitosis} = \\text{Prophase} + \\text{Metaphase} + \\text{Anaphase} + \\text{Telophase}$$', '{"node":"biology","tool_calls":[{"name":"web_search","args":{"query":"mitosis stages diagram"},"id":"seed_mitosis_1"}],"token_usage":{"input_tokens":70,"output_tokens":100,"total_tokens":170}}', 170, NULL),
(5, 'user', 'How long does each stage take?', NULL, 0, 'Chromosomes align at the metaphase plate.'),
(5, 'assistant', 'Typical durations in mammalian cells:\n\n| Stage | Duration |\n|-------|----------|\n| Prophase | ~30-60 min |\n| Metaphase | ~20-30 min |\n| Anaphase | ~5-10 min |\n| Telophase | ~20-30 min |\n\n> Anaphase is the shortest — chromatids move fast at ~1 μm/min.', '{"node":"biology","tool_calls":[{"name":"web_search","args":{"query":"mitosis stage durations mammalian cells"},"id":"seed_mitosis_2"}],"token_usage":{"input_tokens":60,"output_tokens":80,"total_tokens":140}}', 140, NULL),

-- Chat 6: Meiosis vs Mitosis (AP Biology, just-solve)
(6, 'user', 'Difference between meiosis and mitosis?', NULL, 0, NULL),
(6, 'assistant', '| Feature | Mitosis | Meiosis |\n|---------|---------|---------|\n| Divisions | 1 | 2 |\n| Daughter cells | 2 diploid | 4 haploid |\n| Genetic variation | None (identical) | Crossing over & independent assortment |\n| Purpose | Growth, repair | Gamete production |', '{"node":"biology","token_usage":{"input_tokens":60,"output_tokens":90,"total_tokens":150}}', 150, NULL),

-- Chat 7: Civil War causes (US History, guide)
(7, 'user', 'What caused the Civil War?', NULL, 0, NULL),
(7, 'assistant', 'Historians identify **4 primary causes**:\n\n1. **Slavery** — Moral and economic divide between North and South\n2. **States'' Rights** — Southern belief in nullification and secession\n3. **Economic differences** — Industrial North vs. agrarian South\n4. **Political breakdown** — Failure of compromises (Missouri Compromise, Compromise of 1850, Kansas-Nebraska Act)\n\n$$\\text{Secession} \\to \\text{Fort Sumter} \\to \\text{Civil War}$$', '{"node":"history","tool_calls":[{"name":"web_search","args":{"query":"primary causes of US Civil War historiography"},"id":"seed_civilwar_1"}],"token_usage":{"input_tokens":55,"output_tokens":105,"total_tokens":160}}', 160, NULL),
(7, 'user', 'What was the Emancipation Proclamation?', NULL, 0, 'Secession \\to Fort Sumter \\to Civil War'),
(7, 'assistant', 'Issued by **Lincoln** on **January 1, 1863**, it declared slaves in Confederate states **free**.\n\nKey points:\n- Only applied to states *in rebellion* (not border states)\n- Changed the war goal from *preserving the Union* to *ending slavery*\n- Paved the way for the **13th Amendment**\n\n> "All persons held as slaves ... shall be then, thenceforward, and forever free."', '{"node":"history","tool_calls":[{"name":"web_search","args":{"query":"Emancipation Proclamation text and impact"},"id":"seed_civilwar_2"}],"token_usage":{"input_tokens":65,"output_tokens":95,"total_tokens":160}}', 160, NULL),
(7, 'user', 'What role did economics play?', NULL, 0, 'Economic differences \\u2014 Industrial North vs. agrarian South'),
(7, 'assistant', 'The North and South had **divergent economies**:\n\n- **North**: Manufacturing, railroads, wage labor — wanted tariffs to protect industry\n- **South**: Cash-crop agriculture (cotton, tobacco) — relied on slavery and free trade\n\n$$\\text{Tariff of Abominations (1828)} \\to \\text{Nullification Crisis} \\to \\text{Sectional tension}$$', '{"node":"history","token_usage":{"input_tokens":60,"output_tokens":70,"total_tokens":130}}', 130, NULL),

-- Chat 8: Reconstruction (US History, just-solve)
(8, 'user', 'Summarize the Reconstruction era', NULL, 0, NULL),
(8, 'assistant', '**Reconstruction (1865–1877)** — the period after the Civil War when the US reintegrated Southern states and defined freedmen''s rights.\n\nKey developments:\n- **13th Amendment** — abolished slavery\n- **14th Amendment** — citizenship & equal protection\n- **15th Amendment** — Black male suffrage\n- **Freedmen''s Bureau** — education, labor, healthcare\n- **Black Codes & Jim Crow** — systematic discrimination\n\nReconstruction ended with the **Compromise of 1877**, withdrawing federal troops from the South.', '{"node":"history","tool_calls":[{"name":"web_search","args":{"query":"Reconstruction era summary key events"},"id":"seed_recon_1"}],"token_usage":{"input_tokens":50,"output_tokens":130,"total_tokens":180}}', 180, NULL),
(8, 'user', 'What was the Freedmen''s Bureau?', NULL, 0, NULL),
(8, 'assistant', 'The **Freedmen''s Bureau** (1865–1872) was a federal agency that:\n\n- Established **~1,000 schools** for formerly enslaved people\n- Provided **food, housing, and medical aid**\n- Helped negotiate **labor contracts**\n- Reunited **families separated by slavery**\n\nIt was one of the first federal social welfare programs in US history.', '{"node":"history","token_usage":{"input_tokens":40,"output_tokens":70,"total_tokens":110}}', 110, NULL),

-- Chat 9: Limits & continuity (AP Calculus AB, guide)
(9, 'user', 'Explain the formal definition of a limit', NULL, 0, NULL),
(9, 'assistant', 'The **epsilon-delta definition**:\n\n$$\\lim_{x \\to a} f(x) = L \\iff \\forall \\varepsilon > 0, \\; \\exists \\delta > 0 \\text{ such that } 0 < |x - a| < \\delta \\implies |f(x) - L| < \\varepsilon$$\n\nIntuitively: you can make $f(x)$ *arbitrarily close* to $L$ by picking $x$ *sufficiently close* to $a$.', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"limit definition"},"id":"seed_limits_1"}],"token_usage":{"input_tokens":60,"output_tokens":90,"total_tokens":150}}', 150, NULL),
(9, 'user', 'Is $f(x) = \\frac{1}{x}$ continuous at $x = 0$?', NULL, 0, '\\forall \\varepsilon > 0, \\; \\exists \\delta > 0 \\text{ such that } 0 < |x - a| < \\delta \\implies |f(x) - L| < \\varepsilon'),
(9, 'assistant', 'No — $f(x) = \\frac{1}{x}$ is **not continuous** at $x = 0$ because:\n\n$$\\lim_{x \\to 0^-} \\frac{1}{x} = -\\infty \\quad \\text{and} \\quad \\lim_{x \\to 0^+} \\frac{1}{x} = +\\infty$$\n\nThe limit does not exist (infinite discontinuity). For continuity at $a$, we need:\n$$\\lim_{x \\to a} f(x) = f(a)$$\nAnd $f(0)$ is undefined.', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"1/0"},"id":"seed_limits_2"},{"name":"web_search","args":{"query":"infinite discontinuity examples"},"id":"seed_limits_3"}],"token_usage":{"input_tokens":50,"output_tokens":100,"total_tokens":150}}', 150, NULL),

-- Chat 10: Derivative practice (AP Calculus AB, just-solve)
(10, 'user', 'Find the derivative of $f(x) = x^3 \\sin(x)$', NULL, 0, NULL),
(10, 'assistant', 'Use the **product rule**: $\\frac{d}{dx}[u \\cdot v] = u''v + uv''$\n\nLet $u = x^3$, $v = \\sin(x)$:\n\n$$f''(x) = 3x^2 \\cdot \\sin(x) + x^3 \\cdot \\cos(x) = x^2 (3\\sin(x) + x \\cos(x))$$\n\n> Check: at $x = \\pi$, $f''(\\pi) = \\pi^2 (0 + \\pi \\cdot (-1)) = -\\pi^3$', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"derivative of x^3 * sin(x)"},"id":"seed_deriv_1"}],"token_usage":{"input_tokens":40,"output_tokens":100,"total_tokens":140}}', 140, NULL),
(10, 'user', 'Find $\\frac{dy}{dx}$ for $y = \\ln(\\sec(x) + \\tan(x))$', NULL, 0, NULL),
(10, 'assistant', '$$y = \\ln(\\sec x + \\tan x)$$\n\n$$\\frac{dy}{dx} = \\frac{\\sec x \\tan x + \\sec^2 x}{\\sec x + \\tan x} = \\frac{\\sec x (\\tan x + \\sec x)}{\\sec x + \\tan x} = \\sec x$$\n\nSo $\\frac{d}{dx} \\ln(\\sec x + \\tan x) = \\sec x$.', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"derivative of ln(sec(x) + tan(x))"},"id":"seed_deriv_2"}],"token_usage":{"input_tokens":50,"output_tokens":100,"total_tokens":150}}', 150, NULL),

-- Chat 11: Binary trees (Computer Science, guide)
(11, 'user', 'Explain binary search trees', NULL, 0, NULL),
(11, 'assistant', 'A **Binary Search Tree (BST)** is a tree where each node has at most 2 children:\n\n```\n        8\n       / \\\n      3   10\n     / \\    \\\n    1   6    14\n       / \\\n      4   7\n```\n\n**Properties:**\n- Left subtree < node\n- Right subtree > node\n- In-order traversal yields sorted order\n\n**Operations:** `O(h)` where $h = \\text{height}$ (worst $O(n)$, balanced $O(\\log n)$)', '{"node":"cs","tool_calls":[{"name":"web_search","args":{"query":"binary search tree properties and operations"},"id":"seed_bst_1"}],"token_usage":{"input_tokens":60,"output_tokens":110,"total_tokens":170}}', 170, NULL),
(11, 'user', 'Implement a BST in Python', NULL, 0, 'In-order traversal yields sorted order'),
(11, 'assistant', '```python\nclass Node:\n    def __init__(self, val):\n        self.val = val\n        self.left = None\n        self.right = None\n\ndef insert(root, val):\n    if not root:\n        return Node(val)\n    if val < root.val:\n        root.left = insert(root.left, val)\n    else:\n        root.right = insert(root.right, val)\n    return root\n\ndef inorder(root):\n    if root:\n        yield from inorder(root.left)\n        yield root.val\n        yield from inorder(root.right)\n\ndef search(root, val):\n    if not root or root.val == val:\n        return root\n    return search(root.left, val) if val < root.val else search(root.right, val)\n```\n\n**Usage:** `root = insert(None, 8); insert(root, 3); list(inorder(root))  # [3, 8]`', '{"node":"cs","tool_calls":[{"name":"calculator","args":{"expression":"binary search tree insertion complexity"},"id":"seed_bst_2"}],"token_usage":{"input_tokens":70,"output_tokens":120,"total_tokens":190}}', 190, NULL),

-- Chat 12: Sorting algorithms (Computer Science, just-solve)
(12, 'user', 'Compare sorting algorithms', NULL, 0, NULL),
(12, 'assistant', '| Algorithm | Best | Average | Worst | Space | Stable |\n|-----------|------|---------|-------|-------|--------|\n| Bubble | $O(n)$ | $O(n^2)$ | $O(n^2)$ | $O(1)$ | Yes |\n| Selection | $O(n^2)$ | $O(n^2)$ | $O(n^2)$ | $O(1)$ | No |\n| Insertion | $O(n)$ | $O(n^2)$ | $O(n^2)$ | $O(1)$ | Yes |\n| Merge | $O(n \\log n)$ | $O(n \\log n)$ | $O(n \\log n)$ | $O(n)$ | Yes |\n| Quick | $O(n \\log n)$ | $O(n \\log n)$ | $O(n^2)$ | $O(\\log n)$ | No |\n| Heap | $O(n \\log n)$ | $O(n \\log n)$ | $O(n \\log n)$ | $O(1)$ | No |\n\n> **Merge sort** is $O(n \\log n)$ guaranteed. **Quick sort** is faster in practice ($\\times 2$–$3\\times$) but has a worst-case $O(n^2)$.', '{"node":"cs","tool_calls":[{"name":"web_search","args":{"query":"sorting algorithms comparison time complexity"},"id":"seed_sort_1"}],"token_usage":{"input_tokens":40,"output_tokens":120,"total_tokens":160}}', 160, NULL);

-- Duplicate leeyihong03's data for leeshihau (user_id=4)
INSERT INTO subjects (id, user_id, name, created_at) VALUES
    (8, 4, 'AP Biology', (SELECT created_at FROM subjects WHERE id=4)),
    (9, 4, 'US History', (SELECT created_at FROM subjects WHERE id=5)),
    (10, 4, 'AP Calculus AB', (SELECT created_at FROM subjects WHERE id=6)),
    (11, 4, 'Computer Science', (SELECT created_at FROM subjects WHERE id=7));

INSERT INTO chats (id, subject_id, user_id, title, total_tokens, input_tokens, output_tokens, created_at, updated_at) VALUES
    (13, 8, 4, 'Cell division', 490, 210, 280, (SELECT created_at FROM chats WHERE id=5), (SELECT updated_at FROM chats WHERE id=5)),
    (14, 8, 4, 'Meiosis vs Mitosis', 150, 60, 90, (SELECT created_at FROM chats WHERE id=6), (SELECT updated_at FROM chats WHERE id=6)),
    (15, 9, 4, 'Civil War causes', 440, 180, 260, (SELECT created_at FROM chats WHERE id=7), (SELECT updated_at FROM chats WHERE id=7)),
    (16, 9, 4, 'Reconstruction', 220, 90, 130, (SELECT created_at FROM chats WHERE id=8), (SELECT updated_at FROM chats WHERE id=8)),
    (17, 10, 4, 'Limits & continuity', 320, 130, 190, (SELECT created_at FROM chats WHERE id=9), (SELECT updated_at FROM chats WHERE id=9)),
    (18, 10, 4, 'Derivative practice', 240, 100, 140, (SELECT created_at FROM chats WHERE id=10), (SELECT updated_at FROM chats WHERE id=10)),
    (19, 11, 4, 'Binary trees', 390, 160, 230, (SELECT created_at FROM chats WHERE id=11), (SELECT updated_at FROM chats WHERE id=11)),
    (20, 11, 4, 'Sorting algorithms', 210, 90, 120, (SELECT created_at FROM chats WHERE id=12), (SELECT updated_at FROM chats WHERE id=12));

INSERT INTO messages (chat_id, role, content, metadata_json, token_count, quote, created_at)
SELECT
  CASE chat_id
    WHEN 5 THEN 13 WHEN 6 THEN 14 WHEN 7 THEN 15 WHEN 8 THEN 16
    WHEN 9 THEN 17 WHEN 10 THEN 18 WHEN 11 THEN 19 WHEN 12 THEN 20
  END,
  role, content, metadata_json, token_count, quote, created_at
FROM messages WHERE chat_id IN (5,6,7,8,9,10,11,12);
