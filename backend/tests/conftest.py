import importlib
import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["OPENROUTER_API_KEY"] = "sk-test-key"
os.environ["STRUCTURED_LOGGING_PCT"] = "100"


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    os.environ["DATABASE_PATH"] = db_path

    import app.config
    importlib.reload(app.config)

    import app.db
    importlib.reload(app.db)
    app.db.DB_PATH = Path(db_path)
    app.db.init_db()

    yield db_path

    os.environ.pop("DATABASE_PATH", None)


@pytest_asyncio.fixture
async def client(setup_test_db):
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def seed(setup_test_db):
    from app.db import get_conn

    def _seed(*, sql=None, users=None, subjects=None, chats=None):
        if sql:
            with get_conn() as conn:
                conn.executescript(sql)
        if users:
            with get_conn() as conn:
                for email in users:
                    conn.execute("INSERT INTO users (email) VALUES (?)", (email,))
        if subjects:
            with get_conn() as conn:
                for user_id, name in subjects:
                    conn.execute("INSERT INTO subjects (user_id, name) VALUES (?, ?)", (user_id, name))
        if chats:
            with get_conn() as conn:
                for subject_id, user_id, title in chats:
                    conn.execute(
                        "INSERT INTO chats (subject_id, user_id, title) VALUES (?, ?, ?)",
                        (subject_id, user_id, title),
                    )

    return _seed


@pytest.fixture
def auth_token(setup_test_db):
    from app.auth import create_access_token
    from app.db import get_conn
    from app.schemas import User

    def _get_token(email: str = "alice@school.edu") -> str:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not row:
                conn.execute("INSERT INTO users (email) VALUES (?)", (email,))
                row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            user = User(id=row["id"], email=row["email"], created_at=row["created_at"])
            return create_access_token(user)

    return _get_token
