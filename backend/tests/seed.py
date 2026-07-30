INITIAL_SEED = """
INSERT INTO users (id, email, created_at) VALUES
    (1, 'alice@school.edu', '2025-01-01T00:00:00'),
    (2, 'bob@school.edu', '2025-01-01T00:00:00');

INSERT INTO subjects (id, user_id, name, created_at) VALUES
    (1, 1, 'Math', '2025-01-01T00:00:00'),
    (2, 1, 'Physics', '2025-01-01T00:00:00'),
    (3, 2, 'Chemistry', '2025-01-01T00:00:00');

INSERT INTO chats (id, subject_id, user_id, title, total_tokens, input_tokens, output_tokens, created_at, updated_at) VALUES
    (1, 1, 1, 'Algebra Help', 150, 80, 70, '2025-01-01T00:00:00', '2025-01-01T00:00:00'),
    (2, 1, 1, 'Calculus Q', 0, 0, 0, '2025-01-02T00:00:00', '2025-01-02T00:00:00');

INSERT INTO messages (id, chat_id, role, content, token_count, created_at) VALUES
    (1, 1, 'user', 'What is 2+2?', 5, '2025-01-01T00:00:00'),
    (2, 1, 'assistant', 'The answer is 4.', 10, '2025-01-01T00:00:01');
"""
