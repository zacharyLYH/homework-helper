import math
from pathlib import Path
from typing import Any

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)

# Repo-local copy of the embedding model (see scripts/download_embedding_model.py).
# When present it takes precedence over the hub id so we never download at runtime.
_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def _resolve_model_path(name: str) -> str:
    local = _MODELS_DIR / name
    if local.exists():
        return str(local)
    return name

# Representative homework requests, embedded once at startup. A user message is
# rejected when its cosine similarity to the closest corpus sentence falls below
# `settings.homework_alignment_threshold`.
HOMEWORK_CORPUS = [
    "can you help me solve this calculus problem",
    "explain how to factor this quadratic equation step by step",
    "help me understand Newton's second law for my physics homework",
    "how do I find the derivative of this function",
    "what is the answer to this chemistry homework question",
    "help me with my economics homework on supply and demand",
    "guide me through this accounting problem",
    "help me with my statistics homework",
    "walk me through this finance problem",
    "how do I balance this chemical equation",
    "show me how to work out this probability problem",
    "help me understand this concept from my math class",
    "can you check my answer to this homework question",
    "help me with my homework assignment",
    "solve this equation and explain each step",
    "what does this physics formula mean",
    "help me study for my upcoming math test",
    "explain this biology question from my homework",
]


class HuggingFaceEncoder:
    """Local sentence embedding encoder.

    Wraps `sentence_transformers.SentenceTransformer` so the model
    `sentence-transformers/all-MiniLM-L6-v2` is loaded once and reused.
    Kept to the same `name=` API as `semantic_router.encoders.HuggingFaceEncoder`.

    Note: we deliberately do NOT depend on `semantic-router`. Its base
    dependency `litellm>=1.83.7` fails to build on this toolchain (requires
    Rust edition2024), and its `encoders` package imports litellm at import
    time. This wrapper produces identical embeddings (mean-pooled, L2
    normalized) for the same model.
    """

    def __init__(self, name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.name = _resolve_model_path(name)
        self._model: Any | None = None

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            log.info("Loading embedding model: %s", self.name)
            self._model = SentenceTransformer(self.name)
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()


_encoder: HuggingFaceEncoder | None = None
_corpus_embeddings: list[list[float]] | None = None


def _get_encoder() -> HuggingFaceEncoder:
    global _encoder
    if _encoder is None:
        _encoder = HuggingFaceEncoder(name=settings.embedding_model)
    return _encoder


def _get_corpus_embeddings() -> list[list[float]]:
    global _corpus_embeddings
    if _corpus_embeddings is None:
        _corpus_embeddings = _get_encoder().encode(HOMEWORK_CORPUS)
    return _corpus_embeddings


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def check_alignment(text: str) -> tuple[bool, float, str]:
    """Return (allowed, best_score, reason) for a user message.

    Fail closed: if the encoder cannot be loaded or errors, the message is
    rejected rather than passed through unchecked.
    """
    threshold = settings.homework_alignment_threshold
    if not text.strip():
        return False, 0.0, "below_threshold"

    try:
        query_embedding = _get_encoder().encode([text])[0]
        corpus = _get_corpus_embeddings()
        score = max(_cosine_similarity(query_embedding, ref) for ref in corpus)
    except Exception as e:
        log.error("Embedding alignment check failed: %s", e, exc_info=True)
        return False, 0.0, "encoder_unavailable"

    if score >= threshold:
        return True, score, "aligned"
    return False, score, "below_threshold"
