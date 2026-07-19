#!/usr/bin/env bash
set -euo pipefail

echo "=== homework-helper setup ==="

if [ ! -f .env ]; then
  echo "Creating .env"
  touch .env
  echo "
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openrouter/free
JWT_SECRET_KEY=

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=

ENVIRONMENT=dev
" >> .env
fi

echo ""
echo "--- Backend setup ---"
cd backend
uv sync --frozen --no-dev
uv run python -c "from app.db import init_db; init_db()"
uv run python -c "from app.db import seed_db; seed_db()" 2>/dev/null || true
cd ..

echo ""
echo "--- Frontend setup ---"
cd frontend
npm install
cd ..

echo ""
echo "=== Done ==="
echo ""
echo "Start everything:  docker compose up --build"
echo "Or dev mode:       Terminal 1: cd backend && uv run uvicorn app.main:app --reload"
echo "                   Terminal 2: cd frontend && npm run dev"
echo ""
