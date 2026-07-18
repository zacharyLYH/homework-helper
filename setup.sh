#!/usr/bin/env bash
set -euo pipefail

echo "=== homework-helper setup ==="

# --- Backend ---
echo ""
echo "[1/4] Setting up backend..."
cd backend
echo "3.10" > .python-version
uv sync
cd ..

# --- Frontend ---
echo ""
echo "[2/4] Setting up frontend..."
cd frontend
echo "3.10" > .python-version
uv sync
cd ..

# --- Data directory ---
echo ""
echo "[3/4] Creating data directory..."
mkdir -p data
touch data/.gitkeep

# --- .env ---
echo ""
echo "[4/4] Checking .env..."
if [ ! -f "backend/.env" ]; then
  touch backend/.env
  echo "OPENROUTER_API_KEY=
  OPENROUTER_MODEL=" > backend/.env
else
  echo "  backend/.env already exists"
fi

# --- Done ---
echo ""
echo "Done!"
echo ""
echo "To run:"
echo "  Terminal 1 (backend):  cd backend && uv run python -m app.main"
echo "  Terminal 2 (frontend): cd frontend && uv run streamlit run app.py"
echo ""
echo "Or with Docker:"
echo "  docker compose up --build"
