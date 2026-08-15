FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# Embedding model is pre-downloaded into the repo (scripts/download_embedding_model.py)
# and baked into the image so alignment never hits the network at runtime.
COPY models/ ./models/

COPY app/ ./app/
COPY memory/ ./memory/
COPY shared/ ./shared/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
