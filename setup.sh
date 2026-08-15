#!/usr/bin/env bash
set -euo pipefail

echo "=== homework-helper setup ==="

# Only create .env if it does not exist; never overwrite an existing one.
if [ ! -f backend/.env ]; then
  echo "Creating backend/.env"
  touch backend/.env
  echo "
OPENROUTER_API_KEY= # https://openrouter.ai/workspaces/default/keys
OPENROUTER_MODEL=openrouter/free
JWT_SECRET_KEY=KMIXDhiXWcPG9T/UsM+NKpfPjyRbzgXgyyhizOCTesY= #encourage changing via https://randomkeygen.com/jwt-secret
AES_SECRET_KEY=534c6cd141f74f6765f5c00abfba2d4ca589a7e74fd372e1e90aed927e7805b8 # encourage changing via https://randomkeygen.com/encryption-key

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER= # https://www.gmass.co/blog/gmail-smtp/
SMTP_PASSWORD=
SMTP_FROM=

STRUCTURED_LOGGING_PCT=100
ENVIRONMENT=dev

MEMORY_ENABLED=false
MEMORY_STRICT_MODE=true
MEMORY_DATABASE_PATH=data/memory.db
" >> backend/.env
fi

echo ""
echo "--- Backend dependencies ---"
cd backend
if [ ! -d .venv ]; then
  uv sync --frozen
else
  echo "backend/.venv exists; skipping uv sync"
fi

echo ""
echo "--- Reset app + debug databases ---"
cd ..
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 data/homework_helper.db ".read data/purge-and-seed.sql"
else
  echo "sqlite3 not found; cannot reset app database"
  echo "Run: sqlite3 data/homework_helper.db \".read data/purge-and-seed.sql\""
fi
cd backend
uv run python -c "from app.db import init_db; init_db()"
cd ..

echo ""
echo "--- Reset memory database ---"
cd backend
uv run python -c "
from memory.config import REQUIRED_MEMORY_TABLES
from memory.db import get_conn
with get_conn() as conn:
    for table in REQUIRED_MEMORY_TABLES:
        conn.execute(f'DROP TABLE IF EXISTS {table}')
"
uv run python -c "from memory.db import init_db; init_db()"
uv run python -m memory.seed
cd ..

echo ""
echo "--- Embedding model ---"
MODEL_DIR="backend/models/sentence-transformers/all-MiniLM-L6-v2"
if [ -d "$MODEL_DIR" ] && [ -n "$(ls -A "$MODEL_DIR" 2>/dev/null)" ]; then
  echo "Embedding model already downloaded; skipping"
else
  cd backend
  uv run python scripts/download_embedding_model.py
  cd ..
fi

echo ""
echo "--- Regenerate API docs ---"
cd backend
uv run python scripts/generate_api_docs.py
cd ..

echo ""
echo "--- Frontend dependencies ---"
cd frontend
if [ -d node_modules ]; then
  echo "frontend/node_modules exists; skipping npm install"
else
  npm install
fi
cd ..

cd frontend-debug
if [ -d node_modules ]; then
  echo "frontend-debug/node_modules exists; skipping npm install"
else
  npm install
fi
cd ..

echo ""
echo "=== Done ==="
echo ""
echo "Start everything:  docker compose up --build"
echo "Or dev mode:"
echo "  Terminal 1: cd backend && uv run uvicorn app.main:app --reload"
echo "  Terminal 2: cd frontend && npm run dev"
echo "  Terminal 3: cd backend && uv run python -m memory.jobs --poll-interval 2 --batch-size 20"
echo "  Terminal 4: cd frontend-debug && npm run dev"
echo ""