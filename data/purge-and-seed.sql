DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS chats;
DROP TABLE IF EXISTS subjects;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS verification_codes;

-- Sequences reset automatically when the tables are dropped & recreated,
-- so the explicit sqlite_sequence reset is unnecessary (and errors on a
-- fresh DB where the table does not yet exist).

ATTACH DATABASE 'data/debug.db' AS debug;
DROP TABLE IF EXISTS debug.structured_logs;
CREATE TABLE debug.structured_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    message_id INTEGER,
    log TEXT NOT NULL,
    _req_id TEXT NOT NULL
);
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
    drawing_json TEXT,
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

INSERT INTO messages (chat_id, role, content, image_base64, image_media_type, metadata_json, drawing_json, token_count, quote) VALUES
(3, 'user', 'Help me finish this free-body diagram A student drew by hand.', 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAOz8wsAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', 'image/png', '{"is_diagram": true}', NULL, 0, NULL),
(3, 'assistant', 'Sure. Your diagram shows the car at rest with forces: weight W downward, normal N upward. Add a forward friction arrow and label it F.', NULL, NULL, '{"node":"physics","token_usage":{"input_tokens":35,"output_tokens":45,"total_tokens":80}}', NULL, 80, NULL),
(1, 'user', 'What is the chain rule?', NULL, NULL, NULL, NULL, 0, NULL),
(1, 'assistant', 'The chain rule: d/dx[f(g(x))] = f''(g(x)) * g''(x).', NULL, NULL, '{"node":"math","tool_calls":[{"name":"web_search","args":{"query":"chain rule formula"},"id":"seed_call_1"},{"name":"calculator","args":{"expression":"d/dx sin(x^2)"},"id":"seed_call_2"}],"token_usage":{"input_tokens":50,"output_tokens":60,"total_tokens":110}}',
'[{"id":"seed_rect_1","type":"rect","x":40,"y":60,"w":140,"h":60,"stroke":null,"strokeWidth":2,"fill":"#eef2ff","text":"f(x)"},{"id":"seed_rect_2","type":"rect","x":280,"y":60,"w":140,"h":60,"stroke":null,"strokeWidth":2,"fill":"#eef2ff","text":"g(x)"},{"id":"seed_arrow_1","type":"arrow","from_pos":[175,90],"to_pos":[285,90],"stroke":null,"strokeWidth":2,"label":"compose"}]',
 110, NULL),
(1, 'user', 'Can you give me an example?', NULL, NULL, NULL, NULL, 0, 'd/dx[f(g(x))] = f''(g(x)) * g''(x)'),
(1, 'assistant', 'If y = sin(x²), then dy/dx = cos(x²) * 2x.', NULL, NULL, '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"d/dx sin(x^2)"},"id":"seed_call_3"}],"token_usage":{"input_tokens":80,"output_tokens":45,"total_tokens":125}}', NULL, 125, NULL),
(2, 'user', 'Evaluate integral of x*e^x', NULL, NULL, NULL, NULL, 0, NULL),
(2, 'assistant', '∫x*e^x dx = e^x(x-1) + C', NULL, NULL, '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"integral x*e^x"},"id":"seed_call_4"}],"token_usage":{"input_tokens":60,"output_tokens":70,"total_tokens":130}}', NULL, 130, NULL),
(3, 'user', 'Car accelerates from rest at 2m/s². Position at t=5s?', NULL, NULL, NULL, NULL, 0, NULL),
(3, 'assistant', 'x = ½at² = ½ * 2 * 25 = 25 meters', NULL, NULL, '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"0.5 * 2 * 25"},"id":"seed_call_5"}],"token_usage":{"input_tokens":55,"output_tokens":50,"total_tokens":105}}', NULL, 105, NULL),
(4, 'user', 'Difference between SN1 and SN2?', NULL, NULL, NULL, NULL, 0, NULL),
(4, 'assistant', 'SN1: two-step, carbocation, racemization, tertiary. SN2: one-step, backside attack, inversion, primary.', NULL, NULL, '{"node":"general","token_usage":{"input_tokens":45,"output_tokens":65,"total_tokens":110}}', NULL, 110, NULL);

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

INSERT INTO messages (chat_id, role, content, metadata_json, drawing_json, token_count, quote) VALUES
-- Chat 5: Cell division (AP Biology, guide)
(5, 'user', 'Explain the stages of mitosis', NULL, NULL, 0, NULL),
(5, 'assistant', 'Mitosis has **4 main stages**:\n\n1. **Prophase** — Chromosomes condense, nuclear envelope breaks down.\n2. **Metaphase** — Chromosomes align at the metaphase plate.\n3. **Anaphase** — Sister chromatids separate and move to opposite poles.\n4. **Telophase** — Nuclear membranes reform, chromosomes decondense.\n\n$$\\text{Mitosis} = \\text{Prophase} + \\text{Metaphase} + \\text{Anaphase} + \\text{Telophase}$$', '{"node":"biology","tool_calls":[{"name":"web_search","args":{"query":"mitosis stages"},"id":"seed_mitosis_1"}],"token_usage":{"input_tokens":70,"output_tokens":100,"total_tokens":170}}', NULL, 170, NULL),
(5, 'user', 'How long does each stage take?', NULL, NULL, 0, 'Chromosomes align at the metaphase plate.'),
(5, 'assistant', 'Typical durations in mammalian cells:\n\n| Stage | Duration |\n|-------|----------|\n| Prophase | ~30-60 min |\n| Metaphase | ~20-30 min |\n| Anaphase | ~5-10 min |\n| Telophase | ~20-30 min |\n\n> Anaphase is the shortest — chromatids move fast at ~1 μm/min.', '{"node":"biology","tool_calls":[{"name":"web_search","args":{"query":"mitosis stage durations mammalian cells"},"id":"seed_mitosis_2"}],"token_usage":{"input_tokens":60,"output_tokens":80,"total_tokens":140}}', NULL, 140, NULL),

-- Chat 6: Meiosis vs Mitosis (AP Biology, just-solve)
(6, 'user', 'Difference between meiosis and mitosis?', NULL, NULL, 0, NULL),
(6, 'assistant', '| Feature | Mitosis | Meiosis |\n|---------|---------|---------|\n| Divisions | 1 | 2 |\n| Daughter cells | 2 diploid | 4 haploid |\n| Genetic variation | None (identical) | Crossing over & independent assortment |\n| Purpose | Growth, repair | Gamete production |', '{"node":"biology","token_usage":{"input_tokens":60,"output_tokens":90,"total_tokens":150}}', NULL, 150, NULL),

-- Chat 7: Civil War causes (US History, guide)
(7, 'user', 'What caused the Civil War?', NULL, NULL, 0, NULL),
(7, 'assistant', 'Historians identify **4 primary causes**:\n\n1. **Slavery** — Moral and economic divide between North and South\n2. **States'' Rights** — Southern belief in nullification and secession\n3. **Economic differences** — Industrial North vs. agrarian South\n4. **Political breakdown** — Failure of compromises (Missouri Compromise, Compromise of 1850, Kansas-Nebraska Act)\n\n$$\\text{Secession} \\to \\text{Fort Sumter} \\to \\text{Civil War}$$', '{"node":"history","tool_calls":[{"name":"web_search","args":{"query":"primary causes of US Civil War historiography"},"id":"seed_civilwar_1"}],"token_usage":{"input_tokens":55,"output_tokens":105,"total_tokens":160}}', NULL, 160, NULL),
(7, 'user', 'What was the Emancipation Proclamation?', NULL, NULL, 0, 'Secession \\to Fort Sumter \\to Civil War'),
(7, 'assistant', 'Issued by **Lincoln** on **January 1, 1863**, it declared slaves in Confederate states **free**.\n\nKey points:\n- Only applied to states *in rebellion* (not border states)\n- Changed the war goal from *preserving the Union* to *ending slavery*\n- Paved the way for the **13th Amendment**\n\n> "All persons held as slaves ... shall be then, thenceforward, and forever free."', '{"node":"history","tool_calls":[{"name":"web_search","args":{"query":"Emancipation Proclamation text and impact"},"id":"seed_civilwar_2"}],"token_usage":{"input_tokens":65,"output_tokens":95,"total_tokens":160}}', NULL, 160, NULL),
(7, 'user', 'What role did economics play?', NULL, NULL, 0, 'Economic differences \\u2014 Industrial North vs. agrarian South'),
(7, 'assistant', 'The North and South had **divergent economies**:\n\n- **North**: Manufacturing, railroads, wage labor — wanted tariffs to protect industry\n- **South**: Cash-crop agriculture (cotton, tobacco) — relied on slavery and free trade\n\n$$\\text{Tariff of Abominations (1828)} \\to \\text{Nullification Crisis} \\to \\text{Sectional tension}$$', '{"node":"history","token_usage":{"input_tokens":60,"output_tokens":70,"total_tokens":130}}', NULL, 130, NULL),

-- Chat 8: Reconstruction (US History, just-solve)
(8, 'user', 'Summarize the Reconstruction era', NULL, NULL, 0, NULL),
(8, 'assistant', '**Reconstruction (1865–1877)** — the period after the Civil War when the US reintegrated Southern states and defined freedmen''s rights.\n\nKey developments:\n- **13th Amendment** — abolished slavery\n- **14th Amendment** — citizenship & equal protection\n- **15th Amendment** — Black male suffrage\n- **Freedmen''s Bureau** — education, labor, healthcare\n- **Black Codes & Jim Crow** — systematic discrimination\n\nReconstruction ended with the **Compromise of 1877**, withdrawing federal troops from the South.', '{"node":"history","tool_calls":[{"name":"web_search","args":{"query":"Reconstruction era summary key events"},"id":"seed_recon_1"}],"token_usage":{"input_tokens":50,"output_tokens":130,"total_tokens":180}}', NULL, 180, NULL),
(8, 'user', 'What was the Freedmen''s Bureau?', NULL, NULL, 0, NULL),
(8, 'assistant', 'The **Freedmen''s Bureau** (1865–1872) was a federal agency that:\n\n- Established **~1,000 schools** for formerly enslaved people\n- Provided **food, housing, and medical aid**\n- Helped negotiate **labor contracts**\n- Reunited **families separated by slavery**\n\nIt was one of the first federal social welfare programs in US history.', '{"node":"history","token_usage":{"input_tokens":40,"output_tokens":70,"total_tokens":110}}', NULL, 110, NULL),

-- Chat 9: Limits & continuity (AP Calculus AB, guide)
(9, 'user', 'Explain the formal definition of a limit', NULL, NULL, 0, NULL),
(9, 'assistant', 'The **epsilon-delta definition**:\n\n$$\\lim_{x \\to a} f(x) = L \\iff \\forall \\varepsilon > 0, \\; \\exists \\delta > 0 \\text{ such that } 0 < |x - a| < \\delta \\implies |f(x) - L| < \\varepsilon$$\n\nIntuitively: you can make $f(x)$ *arbitrarily close* to $L$ by picking $x$ *sufficiently close* to $a$.', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"limit definition"},"id":"seed_limits_1"}],"token_usage":{"input_tokens":60,"output_tokens":90,"total_tokens":150}}', NULL, 150, NULL),
(9, 'user', 'Is $f(x) = \\frac{1}{x}$ continuous at $x = 0$?', NULL, NULL, 0, '\\forall \\varepsilon > 0, \\; \\exists \\delta > 0 \\text{ such that } 0 < |x - a| < \\delta \\implies |f(x) - L| < \\varepsilon'),
(9, 'assistant', 'No — $f(x) = \\frac{1}{x}$ is **not continuous** at $x = 0$ because:\n\n$$\\lim_{x \\to 0^-} \\frac{1}{x} = -\\infty \\quad \\text{and} \\quad \\lim_{x \\to 0^+} \\frac{1}{x} = +\\infty$$\n\nThe limit does not exist (infinite discontinuity). For continuity at $a$, we need:\n$$\\lim_{x \\to a} f(x) = f(a)$$\nAnd $f(0)$ is undefined.', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"1/0"},"id":"seed_limits_2"},{"name":"web_search","args":{"query":"infinite discontinuity examples"},"id":"seed_limits_3"}],"token_usage":{"input_tokens":50,"output_tokens":100,"total_tokens":150}}', NULL, 150, NULL),

-- Chat 10: Derivative practice (AP Calculus AB, just-solve)
(10, 'user', 'Find the derivative of $f(x) = x^3 \\sin(x)$', NULL, NULL, 0, NULL),
(10, 'assistant', 'Use the **product rule**: $\\frac{d}{dx}[u \\cdot v] = u''v + uv''$\n\nLet $u = x^3$, $v = \\sin(x)$:\n\n$$f''(x) = 3x^2 \\cdot \\sin(x) + x^3 \\cdot \\cos(x) = x^2 (3\\sin(x) + x \\cos(x))$$\n\n> Check: at $x = \\pi$, $f''(\\pi) = \\pi^2 (0 + \\pi \\cdot (-1)) = -\\pi^3$', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"derivative of x^3 * sin(x)"},"id":"seed_deriv_1"}],"token_usage":{"input_tokens":40,"output_tokens":100,"total_tokens":140}}', NULL, 140, NULL),
(10, 'user', 'Find $\\frac{dy}{dx}$ for $y = \\ln(\\sec(x) + \\tan(x))$', NULL, NULL, 0, NULL),
(10, 'assistant', '$$y = \\ln(\\sec x + \\tan x)$$\n\n$$\\frac{dy}{dx} = \\frac{\\sec x \\tan x + \\sec^2 x}{\\sec x + \\tan x} = \\frac{\\sec x (\\tan x + \\sec x)}{\\sec x + \\tan x} = \\sec x$$\n\nSo $\\frac{d}{dx} \\ln(\\sec x + \\tan x) = \\sec x$.', '{"node":"math","tool_calls":[{"name":"calculator","args":{"expression":"derivative of ln(sec(x) + tan(x))"},"id":"seed_deriv_2"}],"token_usage":{"input_tokens":50,"output_tokens":100,"total_tokens":150}}', NULL, 150, NULL),

-- Chat 11: Binary trees (Computer Science, guide)
(11, 'user', 'Explain binary search trees', NULL, NULL, 0, NULL),
(11, 'assistant', 'A **Binary Search Tree (BST)** is a tree where each node has at most 2 children:\n\n```\n        8\n       / \\\n      3   10\n     / \\    \\\n    1   6    14\n       / \\\n      4   7\n```\n\n**Properties:**\n- Left subtree < node\n- Right subtree > node\n- In-order traversal yields sorted order\n\n**Operations:** `O(h)` where $h = \\text{height}$ (worst $O(n)$, balanced $O(\\log n)$)', '{"node":"cs","tool_calls":[{"name":"web_search","args":{"query":"binary search tree properties and operations"},"id":"seed_bst_1"}],"token_usage":{"input_tokens":60,"output_tokens":110,"total_tokens":170}}',
'[{"id":"seed_bst_rect_1","type":"rect","x":180,"y":30,"w":70,"h":40,"stroke":null,"strokeWidth":2,"fill":"#eef2ff","text":"8"},{"id":"seed_bst_rect_2","type":"rect","x":60,"y":110,"w":70,"h":40,"stroke":null,"strokeWidth":2,"fill":"#eef2ff","text":"3"},{"id":"seed_bst_rect_3","type":"rect","x":310,"y":110,"w":70,"h":40,"stroke":null,"strokeWidth":2,"fill":"#eef2ff","text":"10"},{"id":"seed_bst_arrow_1","type":"arrow","from_pos":[205,72],"to_pos":[90,108],"stroke":null,"strokeWidth":2,"label":"left"},{"id":"seed_bst_arrow_2","type":"arrow","from_pos":[230,72],"to_pos":[330,108],"stroke":null,"strokeWidth":2,"label":"right"}]',
 170, NULL),
(11, 'user', 'Implement a BST in Python', NULL, NULL, 0, 'In-order traversal yields sorted order'),
(11, 'assistant', '```python\nclass Node:\n    def __init__(self, val):\n        self.val = val\n        self.left = None\n        self.right = None\n\ndef insert(root, val):\n    if not root:\n        return Node(val)\n    if val < root.val:\n        root.left = insert(root.left, val)\n    else:\n        root.right = insert(root.right, val)\n    return root\n\ndef inorder(root):\n    if root:\n        yield from inorder(root.left)\n        yield root.val\n        yield from inorder(root.right)\n\ndef search(root, val):\n    if not root or root.val == val:\n        return root\n    return search(root.left, val) if val < root.val else search(root.right, val)\n```\n\n**Usage:** `root = insert(None, 8); insert(root, 3); list(inorder(root))  # [3, 8]`', '{"node":"cs","tool_calls":[{"name":"calculator","args":{"expression":"binary search tree insertion complexity"},"id":"seed_bst_2"}],"token_usage":{"input_tokens":70,"output_tokens":120,"total_tokens":190}}', NULL, 190, NULL),

-- Chat 12: Sorting algorithms (Computer Science, just-solve)
(12, 'user', 'Compare sorting algorithms', NULL, NULL, 0, NULL),
(12, 'assistant', '| Algorithm | Best | Average | Worst | Space | Stable |\n|-----------|------|---------|-------|-------|--------|\n| Bubble | $O(n)$ | $O(n^2)$ | $O(n^2)$ | $O(1)$ | Yes |\n| Selection | $O(n^2)$ | $O(n^2)$ | $O(n^2)$ | $O(1)$ | No |\n| Insertion | $O(n)$ | $O(n^2)$ | $O(n^2)$ | $O(1)$ | Yes |\n| Merge | $O(n \\log n)$ | $O(n \\log n)$ | $O(n \\log n)$ | $O(n)$ | Yes |\n| Quick | $O(n \\log n)$ | $O(n \\log n)$ | $O(n^2)$ | $O(\\log n)$ | No |\n| Heap | $O(n \\log n)$ | $O(n \\log n)$ | $O(n \\log n)$ | $O(1)$ | No |\n\n> **Merge sort** is $O(n \\log n)$ guaranteed. **Quick sort** is faster in practice ($\\times 2$–$3\\times$) but has a worst-case $O(n^2)$.', '{"node":"cs","tool_calls":[{"name":"web_search","args":{"query":"sorting algorithms comparison time complexity"},"id":"seed_sort_1"}],"token_usage":{"input_tokens":40,"output_tokens":120,"total_tokens":160}}', NULL, 160, NULL);


INSERT INTO messages (chat_id, role, content, image_base64, image_media_type, metadata_json, drawing_json, token_count, quote) VALUES
  (5, 'user', 'I sketched the stages of mitosis — label each one and lay them out in order.', 'iVBORw0KGgoAAAANSUhEUgAAAHgAAAB4CAIAAAC2BqGFAAABxElEQVR4nO3dQU7DQBBE0RyM+x8qG0BiAYmiJNgzVd3V/6sOMPOwvIrM5Xr9ZIJd7CcYMqCBzhrQQGcNaKCzBjTQWQMa6KwBDXTWgAY6a0ADnTWggc5aS+jv7GeIgj6Q/cxtoBdmv0tF6K3Zb1cCWtZcaEuzoO2NgC5SMnTBqkB/0H86CO0+dst4ohU539GNcr6j5yj/1BK6ac2gW9cGOiCgRTWAjqk0dFhAiyoKHRnQospBBwe0qELQ8QEtCmhRJaCHBLQooEUBLcoMPSqgRQEtCmhRQIsCWhTQojZCu3/M1qyD0O5jt4wnWhHv6DVtfEcD/TegRQEtCmhRQIsCWpQTeo71SSWg3w1oUUCL8kNPsD5PBPRbAS2qCnS29RIfoF9XCzrVehUO0C+qCJ1nvVAG6GfVhU6yXsvC1w0et9wE6Mf1gO5uvQOEbyrdt0mDr4TdtI+C7979ttWB396t7CC0+9gt44lW5HxHF39fy+7OF9FzoStY66/Mf60YAC3m9l7TDy3gtt+uEPQOcftdSkOfRLefuSX0kz+A/QwjoDsOaKCzBjTQWQMa6KwBDXTWgAY6a0ADnTWggc4a0EBnDWigs/YFugyVXjYRp0EAAAAASUVORK5CYII=', 'image/png', '{"is_diagram": true}', NULL, 28, NULL),
  (5, 'assistant', 'Here''s the mitotic sequence left-to-right: Prophase (chromosomes condense), Metaphase (align on the plate), Anaphase (sister chromatids split), Telophase (envelopes reform).', NULL, NULL, '{"node":"biology","token_usage":{"input_tokens":60,"output_tokens":90,"total_tokens":150}}', '[{"type":"rect","id":"m1","x":30,"y":40,"w":150,"h":60,"label":"Prophase","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","id":"m2","x":220,"y":40,"w":150,"h":60,"label":"Metaphase","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","id":"m3","x":410,"y":40,"w":150,"h":60,"label":"Anaphase","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","id":"m4","x":600,"y":40,"w":150,"h":60,"label":"Telophase","stroke":"#3b82f6","strokeWidth":2},{"type":"arrow","id":"a1","from_pos":[185,70],"to_pos":[215,70],"stroke":"#94a3b8","strokeWidth":2},{"type":"arrow","id":"a2","from_pos":[375,70],"to_pos":[405,70],"stroke":"#94a3b8","strokeWidth":2},{"type":"arrow","id":"a3","from_pos":[565,70],"to_pos":[595,70],"stroke":"#94a3b8","strokeWidth":2}]', 64, NULL),
  (6, 'user', 'Draw the two cell divisions side by side so I can compare mitosis vs meiosis.', 'iVBORw0KGgoAAAANSUhEUgAAAHgAAAB4CAIAAAC2BqGFAAABxElEQVR4nO3dQU7DQBBE0RyM+x8qG0BiAYmiJNgzVd3V/6sOMPOwvIrM5Xr9ZIJd7CcYMqCBzhrQQGcNaKCzBjTQWQMa6KwBDXTWgAY6a0ADnTWggc5aS+jv7GeIgj6Q/cxtoBdmv0tF6K3Zb1cCWtZcaEuzoO2NgC5SMnTBqkB/0H86CO0+dst4ohU539GNcr6j5yj/1BK6ac2gW9cGOiCgRTWAjqk0dFhAiyoKHRnQospBBwe0qELQ8QEtCmhRJaCHBLQooEUBLcoMPSqgRQEtCmhRQIsCWhTQojZCu3/M1qyD0O5jt4wnWhHv6DVtfEcD/TegRQEtCmhRQIsCWpQTeo71SSWg3w1oUUCL8kNPsD5PBPRbAS2qCnS29RIfoF9XCzrVehUO0C+qCJ1nvVAG6GfVhU6yXsvC1w0et9wE6Mf1gO5uvQOEbyrdt0mDr4TdtI+C7979ttWB396t7CC0+9gt44lW5HxHF39fy+7OF9FzoStY66/Mf60YAC3m9l7TDy3gtt+uEPQOcftdSkOfRLefuSX0kz+A/QwjoDsOaKCzBjTQWQMa6KwBDXTWgAY6a0ADnTWggc4a0EBnDWigs/YFugyVXjYRp0EAAAAASUVORK5CYII=', 'image/png', '{"is_diagram": true}', NULL, 28, NULL),
  (6, 'assistant', 'Left is mitosis (one division, two identical diploid daughters); right is meiosis (two divisions, four haploid gametes).', NULL, NULL, '{"node":"biology","token_usage":{"input_tokens":55,"output_tokens":85,"total_tokens":140}}', '[{"type":"rect","id":"mit_h","x":30,"y":180,"w":160,"h":60,"label":"Mitosis","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","id":"mit_a","x":30,"y":280,"w":70,"h":40,"label":"a","stroke":"#94a3b8","strokeWidth":2},{"type":"rect","id":"mit_b","x":120,"y":280,"w":70,"h":40,"label":"b","stroke":"#94a3b8","strokeWidth":2},{"type":"rect","id":"mei_h","x":430,"y":180,"w":160,"h":60,"label":"Meiosis","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","id":"mei_a","x":430,"y":280,"w":70,"h":40,"label":"a","stroke":"#94a3b8","strokeWidth":2},{"type":"rect","id":"mei_b","x":520,"y":280,"w":70,"h":40,"label":"b","stroke":"#94a3b8","strokeWidth":2},{"type":"rect","id":"mei_c","x":430,"y":360,"w":70,"h":40,"label":"c","stroke":"#94a3b8","strokeWidth":2},{"type":"rect","id":"mei_d","x":520,"y":360,"w":70,"h":40,"label":"d","stroke":"#94a3b8","strokeWidth":2}]', 64, NULL),
  (7, 'user', 'Map out the events leading to the Civil War on a timeline.', 'iVBORw0KGgoAAAANSUhEUgAAAIwAAABkCAIAAADbtU+GAAABMElEQVR4nO3WwQmDQABFQQtLJRaRc4pIJVaSIqzES3IJBIToTX0wn3ffhUHcYVneunjD6TfQbpACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQq0g3SzC2wL6ey72Xd/kc6+mP3mSwrMPykwr7tAkAJBCgQpEKRAkAJBCrSDNI/jMa3PncZjWp17n+ZjWp37eD03ggQJEiRIkCBBggQJEiRIkCBBggQJEiRIkCBBggQJEiRIkCDtIekKQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQB8UPjo6iJMrGgAAAABJRU5ErkJggg==', 'image/png', '{"is_diagram": true}', NULL, 28, NULL),
  (7, 'assistant', 'Missouri Compromise (1820), Compromise of 1850, Kansas-Nebraska Act (1854), then secession and Fort Sumter (1861).', NULL, NULL, '{"node":"history","token_usage":{"input_tokens":50,"output_tokens":80,"total_tokens":130}}', '[{"type":"rect","x":40,"y":200,"w":100,"h":50,"label":"1820","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":180,"y":200,"w":100,"h":50,"label":"1850","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":320,"y":200,"w":130,"h":50,"label":"1854","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":490,"y":200,"w":120,"h":50,"label":"1861","stroke":"#dc2626","strokeWidth":2},{"type":"arrow","id":"t1","from_pos":[145,225],"to_pos":[175,225],"stroke":"#94a3b8","strokeWidth":2},{"type":"arrow","id":"t2","from_pos":[285,225],"to_pos":[315,225],"stroke":"#94a3b8","strokeWidth":2},{"type":"arrow","id":"t3","from_pos":[455,225],"to_pos":[485,225],"stroke":"#94a3b8","strokeWidth":2}]', 64, NULL),
  (8, 'user', 'Draw a quick diagram of the Reconstruction amendments and what each changed.', 'iVBORw0KGgoAAAANSUhEUgAAAIwAAABkCAIAAADbtU+GAAABMElEQVR4nO3WwQmDQABFQQtLJRaRc4pIJVaSIqzES3IJBIToTX0wn3ffhUHcYVneunjD6TfQbpACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQq0g3SzC2wL6ey72Xd/kc6+mP3mSwrMPykwr7tAkAJBCgQpEKRAkAJBCrSDNI/jMa3PncZjWp17n+ZjWp37eD03ggQJEiRIkCBBggQJEiRIkCBBggQJEiRIkCBBggQJEiRIkCDtIekKQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQJACQQoEKRCkQB8UPjo6iJMrGgAAAABJRU5ErkJggg==', 'image/png', '{"is_diagram": true}', NULL, 28, NULL),
  (8, 'assistant', '13th (abolished slavery), 14th (citizenship & equal protection), 15th (Black male suffrage).', NULL, NULL, '{"node":"history","token_usage":{"input_tokens":45,"output_tokens":70,"total_tokens":115}}', '[{"type":"rect","x":40,"y":200,"w":150,"h":70,"label":"13th: abolish","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":240,"y":200,"w":150,"h":70,"label":"14th: citizenship","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":440,"y":200,"w":150,"h":70,"label":"15th: suffrage","stroke":"#3b82f6","strokeWidth":2},{"type":"arrow","id":"r1","from_pos":[195,235],"to_pos":[235,235],"stroke":"#94a3b8","strokeWidth":2},{"type":"arrow","id":"r2","from_pos":[395,235],"to_pos":[435,235],"stroke":"#94a3b8","strokeWidth":2}]', 64, NULL),
  (9, 'user', 'Sketch what a limit approaching a from both sides looks like on a graph.', 'iVBORw0KGgoAAAANSUhEUgAAAMgAAAB4CAIAAAA48Cq8AAACg0lEQVR4nO3cO3IbMRBFUa1J8azTa/KamNgsQXZRsmjxM2/QAE7XCRhOo26BnIQvp9Mv2N1L9ydgSsIiQlhEdAtr27buy5PTJ6ztz3TfnxBhESEsIoRFhLCIEBYRwiJCWEQIiwhhESEsIoRFhLCIEBYRncP6+fra/QhI6BDWOabLsJruB8G++t9Yl7ofB3upFZa8plExLHlNoMRbobzmUyKsRl4zKRRWI685lAurkdfoiobVyGtcpcNq5DWiAcJq5DWWYcJq5DWKwcJq5FXfkGE18qps4LAaedU0fFiNvKqZJKxGXnVMFVYjrwomDKuRV1/ThtXIq5fJw2rkdbwlwmrkdaSFwmrkdYzlwmrklbZoWI28cpYOq5FXgrDeyWtfwvpAXnsR1hfk9TxhXSWvZwjrG/J6jLBuIq97CesO8rqdsO4mr1sI60Hy+j9hPUVe1whrB/L6l7B2I69LPf41+cffrrbz5+5HsPN28nojrMyOy+d1dFjnkj6FNWtbp7XzcmPl910yL2EdtfVieXkrPNQ6eQmrgxXyElY3c+clrM5mzUtYJcyXl7AKmSkvYZUzR17CKmr0vIRV2rh5CWsAI+YlrGGMlZewBjNKXsIaUv28hDWwynkJa3g18xLWJKrlJayp1MlLWBOqkJewptU3L2FNrldewlrC8XkJayFH5iWs5RyTl7AWlc5LWEvL5SUsInkJi3f7tiUsPtirLWHxBTcWQX5jUY6wiBAWEcIiQlhECIuIb8LajLk+D4bV+7HNAOPGMvvP41+FIbc8GUMTFhHCIkJYRAiLCGERISwihEWEsIgQFhHCIkJYRAiLCGER0Ses01tb3Zcnp1tYzE1YRAiLiN+lxHazF7dv/QAAAABJRU5ErkJggg==', 'image/png', '{"is_diagram": true}', NULL, 28, NULL),
  (9, 'assistant', 'The curve approaches L as x approaches a from left and right; the open dot is the limit value L.', NULL, NULL, '{"node":"math","token_usage":{"input_tokens":55,"output_tokens":85,"total_tokens":140}}', '[{"type":"line","id":"x_axis","points":[[0,190],[560,190]],"stroke":"#94a3b8","strokeWidth":2},{"type":"line","id":"y_axis","points":[[100,10],[100,240]],"stroke":"#94a3b8","strokeWidth":2},{"type":"line","id":"curve","points":[[120,150],[220,120],[300,120],[400,170]],"stroke":"#3b82f6","strokeWidth":3},{"type":"line","id":"lead_l","points":[[160,140],[240,100]],"stroke":"#dc2626","strokeWidth":2},{"type":"line","id":"lead_r","points":[[330,120],[360,150]],"stroke":"#dc2626","strokeWidth":2},{"type":"ellipse","id":"pt","cx":300,"cy":120,"rx":6,"ry":6,"stroke":"#dc2626","strokeWidth":2}]', 64, NULL),
  (10, 'user', 'Draw the graph and the tangent line so I can see how the derivative relates to the slope.', 'iVBORw0KGgoAAAANSUhEUgAAAMgAAAB4CAIAAAA48Cq8AAACg0lEQVR4nO3cO3IbMRBFUa1J8azTa/KamNgsQXZRsmjxM2/QAE7XCRhOo26BnIQvp9Mv2N1L9ydgSsIiQlhEdAtr27buy5PTJ6ztz3TfnxBhESEsIoRFhLCIEBYRwiJCWEQIiwhhESEsIoRFhLCIEBYRncP6+fra/QhI6BDWOabLsJruB8G++t9Yl7ofB3upFZa8plExLHlNoMRbobzmUyKsRl4zKRRWI685lAurkdfoiobVyGtcpcNq5DWiAcJq5DWWYcJq5DWKwcJq5FXfkGE18qps4LAaedU0fFiNvKqZJKxGXnVMFVYjrwomDKuRV1/ThtXIq5fJw2rkdbwlwmrkdaSFwmrkdYzlwmrklbZoWI28cpYOq5FXgrDeyWtfwvpAXnsR1hfk9TxhXSWvZwjrG/J6jLBuIq97CesO8rqdsO4mr1sI60Hy+j9hPUVe1whrB/L6l7B2I69LPf41+cffrrbz5+5HsPN28nojrMyOy+d1dFjnkj6FNWtbp7XzcmPl910yL2EdtfVieXkrPNQ6eQmrgxXyElY3c+clrM5mzUtYJcyXl7AKmSkvYZUzR17CKmr0vIRV2rh5CWsAI+YlrGGMlZewBjNKXsIaUv28hDWwynkJa3g18xLWJKrlJayp1MlLWBOqkJewptU3L2FNrldewlrC8XkJayFH5iWs5RyTl7AWlc5LWEvL5SUsInkJi3f7tiUsPtirLWHxBTcWQX5jUY6wiBAWEcIiQlhECIuIb8LajLk+D4bV+7HNAOPGMvvP41+FIbc8GUMTFhHCIkJYRAiLCGERISwihEWEsIgQFhHCIkJYRAiLCGER0Ses01tb3Zcnp1tYzE1YRAiLiN+lxHazF7dv/QAAAABJRU5ErkJggg==', 'image/png', '{"is_diagram": true}', NULL, 28, NULL),
  (10, 'assistant', 'The tangent line touches the curve at the point; its slope f''(x) is the derivative there.', NULL, NULL, '{"node":"math","tool_calls":[{"name":"draw_elements","args":{},"id":"maths_deriv_1"}],"token_usage":{"input_tokens":50,"output_tokens":90,"total_tokens":140}}', '[{"type":"line","id":"x_axis","points":[[0,190],[560,190]],"stroke":"#94a3b8","strokeWidth":2},{"type":"line","id":"y_axis","points":[[100,10],[100,240]],"stroke":"#94a3b8","strokeWidth":2},{"type":"line","id":"curve_p","points":[[120,170],[200,120],[300,140],[400,60]],"stroke":"#3b82f6","strokeWidth":3},{"type":"line","id":"tangent","points":[[135,210],[390,15]],"stroke":"#dc2626","strokeWidth":2},{"type":"ellipse","id":"pt","cx":300,"cy":140,"rx":6,"ry":6,"stroke":"#dc2626","strokeWidth":2}]', 64, NULL),
  (11, 'user', 'Visualize where inserting 5 lands in this binary search tree.', 'iVBORw0KGgoAAAANSUhEUgAAAMgAAAB4CAIAAAA48Cq8AAADKElEQVR4nO3cTW7bQBBEYR9MR8whcpyciZskjBT9UDRlk1Pq6u4nvFXgxbDmiyDAhj6m6TfR8D7CT0AlAxZJAhZJAtY3+vnrR/gZsgSsrf5K2i78hLYBa72XpOC1HbCWfYsUvD4LWA/tVoWtRcC6dVAVtu4D1qUhqrB1DVhzA1Vh6xyw5oA1PGCNV4WtCVgTsDR1hyVShS1gAUsSsIAlCVjAkgQsYElqDUuqqrmt1rAm3rFkAQtYkoAFLEnAApYkYAFLUndYE78r1AQsYEkC1hyqhgesOWAND1iXUDU2YN1C1cCA9RCqRgWsZagaErDWg9TBgLXe6d/rJanzj4Wf1jBgrXT6/1r8+/Ob0+nuFX5sq4C1bAcUbD0HrId2E8HWImDdOogDW/cB69IQFnzkugasubEasDUBS/Qeg63WsKTX39xWX1hvuPjOH7mawnrnffe01RHW+2+6oa12sKLuuJutXrBib7fVR65GsEwu1eQY6lrAcnursDqMqPqwPG/R81QDKw7L+f7c3kfHVhlWimtLccgdlYWV6MISHfXr1YSV7qrSHfhlBWElvaRiH7mqwcp+N9nPf60OrDL/42s8RRFYNS6j0uNUgFXgGjYeKulzpYeVev3CT5cbVt7dyz9jYlhJF2/ypDlgbXxpQvjZ3tPGRy7Pr7sxhcXXvKx2fuoUX6tkB4svpqoxjhEsvkqv0jgusHYP18FWxnEsYB0crratpOPEwxoyXFVbeccJhjVwuHq2Uo8DLN9SjxMJa/hwlWxlHwdYpmUfJwyWaLgatgqMAyzHCowDLMcKjAMsxwqMAyzHCowTA0s6XHZbNcbhHcuxAuMAy7EC4wDLsQLjAMuxAuMAy7EC4/C7QtOyjwMs07KPw99j+ZZ6HGD5lnoc/ubdurzjxMMaNV/4UzDOfRawjs8Xfn7GWeQC68h84SdnnOeMYO1YMPy0jPNZdrC+uGD4CRlnO1NYz1OGn8E2z3FywKJ0AYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYskAYsk/QHdMI2gIfSNMwAAAABJRU5ErkJggg==', 'image/png', '{"is_diagram": true}', NULL, 28, NULL),
  (11, 'assistant', '5 walks right from 3 to 6, then left — it slots in as 6''s left child. Each comparison halves the search space.', NULL, NULL, '{"node":"cs","token_usage":{"input_tokens":60,"output_tokens":95,"total_tokens":155}}', '[{"type":"rect","x":250,"y":40,"w":70,"h":40,"label":"8","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":130,"y":130,"w":70,"h":40,"label":"3","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":370,"y":130,"w":70,"h":40,"label":"10","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":60,"y":220,"w":70,"h":40,"label":"1","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":160,"y":220,"w":70,"h":40,"label":"6","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":200,"y":320,"w":70,"h":40,"label":"5","stroke":"#dc2626","strokeWidth":2},{"type":"arrow","id":"b1","from_pos":[230,120],"to_pos":[160,125],"stroke":"#94a3b8","strokeWidth":2},{"type":"arrow","id":"b2","from_pos":[230,130],"to_pos":[330,125],"stroke":"#94a3b8","strokeWidth":2},{"type":"arrow","id":"b3","from_pos":[195,170],"to_pos":[210,315],"stroke":"#94a3b8","strokeWidth":2}]', 64, NULL),
  (12, 'user', 'Visualize bubble sort on this array step by step.', 'iVBORw0KGgoAAAANSUhEUgAAAMgAAAB4CAIAAAA48Cq8AAACgElEQVR4nO3S0WldARDEUJf9yklhrsQ/TgNhIQ8vd2UOqAAxo4+vr2/gx/l43AC/EmFhBWFhBWFhBWFhBWFhBWFhBWFhBWFhBWGd4PP1epvH5f+JsE4gLKwgLKwgLKwgLKwgLKwgLKwgLKwgLKwgLKwgLKwgLKwgLKwgLKwgLKwgLKwgLKwgLKwgLKwgrADFk4rOM8I6cVLReUZYJ04qOs8I68RJRecZYZ04qeg8I6wTJxWdZ4R14qSi84ywTpxUdJ4R1omTis4zwjpxUtF5RlgnTio6zwjrxElF5xlhnTip6DwjrBMnFZ1nhHXipKLzjLBOnFR0nhHWiZOKzjPCOnFS0XlGWCdOKjrPCOvESUXnGWGdOKnoPCOsEycVnWeEdeKkovOMsE6cVHSeEdaJk4rOM8I6cVLReUZYJ04qOs8I68RJRecZYZ04qeg8I6wTJxWdZ4T1Hye9/ny+zVPOTyEsYa0gLGGtICxhrSAsYa0gLGGtICxhrSAsYa0gLGGtICxhrfBYWMWTis7CCpxUdBZW4KSis7ACJxWdhRU4qegsrMBJRWdhBU4qOgsrcFLRWViBk4rOwgqcVHQWVuCkorOwAicVnYUVOKnoLKzASUVnYQVOKjoLK3BS0VlYgZOKzsIKnFR0FlbgpKKzsAInFZ2PhrU3ZfGkorOwAicVnYUVOKnoLKzASUVnYQVOKjoLK3BS0VlYgZOKzsIKnFR0FlbgpKKzsAInFZ2FFTip6CyswElFZ2EFTio6CytwUtFZWIGTis7CCpxUdBZW4KSis7ACJxWdhRU4qegsrMBJReejYQHvISysICysICysICysICysICysICysICysICys8BfGycgehK3EdQAAAABJRU5ErkJggg==', 'image/png', '{"is_diagram": true}', NULL, 28, NULL),
  (12, 'assistant', 'Compare adjacent pairs and swap when out of order: 5 and 3 swap first; the largest value bubbles to the end each pass.', NULL, NULL, '{"node":"cs","token_usage":{"input_tokens":40,"output_tokens":90,"total_tokens":130}}', '[{"type":"rect","x":40,"y":120,"w":60,"h":80,"label":"3","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":120,"y":120,"w":60,"h":160,"label":"5","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":200,"y":120,"w":60,"h":60,"label":"2","stroke":"#3b82f6","strokeWidth":2},{"type":"rect","x":280,"y":120,"w":60,"h":180,"label":"9","stroke":"#3b82f6","strokeWidth":2},{"type":"arrow","id":"sw1","from_pos":[90,90],"to_pos":[170,90],"stroke":"#dc2626","strokeWidth":2}]', 64, NULL);


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

INSERT INTO messages (chat_id, role, content, image_base64, image_media_type, metadata_json, drawing_json, token_count, quote, created_at)
SELECT
  CASE chat_id
    WHEN 5 THEN 13 WHEN 6 THEN 14 WHEN 7 THEN 15 WHEN 8 THEN 16
    WHEN 9 THEN 17 WHEN 10 THEN 18 WHEN 11 THEN 19 WHEN 12 THEN 20
  END,
  role, content, image_base64, image_media_type, metadata_json, drawing_json, token_count, quote, created_at
FROM messages WHERE chat_id IN (5,6,7,8,9,10,11,12);
