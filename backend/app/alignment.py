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
#
# The corpus is modeled on real student messages mined from the MathMentorDB
# corpus (5.5M student-tutor exchanges): students rarely write "help me". They
# paste the problem, describe what they already know, or ask a specific
# question. Entries below are those recurring patterns, generalized and
# stripped of math-specific vocabulary so matching stays subject-agnostic and
# liberal. A few direct "help me" anchors are kept since they still occur.
HOMEWORK_CORPUS = [
    # Direct help anchors.
    "help me with my homework",
    "help me with this problem",
    "help me understand this",
    "help me with my assignment",
    "walk me through this step by step",
    "can you help me with this",
    "i need help with this problem",
    "someone please help me with this",
    # Content-first: student pastes the problem and says they are stuck.
    "i am stuck on this homework question",
    "i have this problem for homework",
    "this is the question from my homework",
    "i have homework questions and i tried them",
    "this is my homework and i am stuck",
    "i need help with the question at the top",
    "i am stuck on this question",
    "i have been working on this problem",
    # Task-verb asks (problem-solving verbs, not math-specific).
    "how do i solve this",
    "how do i find the answer",
    "how do i approach this problem",
    "which formula is used here",
    "how do i work this out",
    "what is the next step in this problem",
    "how do i do this step by step",
    "what is the first thing i should do",
    "how do i prove this",
    "how do i factor this",
    "how do i simplify this",
    "how do i integrate this",
    "how do i differentiate this",
    "how do i find the derivative of this function",
    "how do i find the integral of this",
    "how do i evaluate this expression",
    "what is the expectation of this",
    "how do i find this value",
    "how do i find the area of this",
    "what is the area of this shape",
    "show me how to solve this",
    # "Here is my work" / confirm-my-work.
    "is my answer correct",
    "did i do this right",
    "can someone check my work",
    "i got an answer, can someone confirm it",
    "i did the work but i am not sure it is right",
    "i am looking for someone to confirm my results",
    "is my reasoning here correct",
    "i got a different answer, which is right",
    # Confusion / stuck mid-way.
    "i do not understand this problem",
    "i am confused about this question",
    "i do not remember how to do this",
    "i am too confused to understand this",
    "i do not know what to do with the next part",
    "i solved the first part but not the rest",
    "i keep getting the wrong answer",
    "what am i doing wrong",
    "i am struggling with this",
    "i do not understand the concept",
    # Why / clarifying questions.
    "why is this the answer",
    "why does this method work",
    "can you explain why this is correct",
    "i do not understand why this happens",
    "is there a simpler way to do this",
    "what do you mean by that",
    "am i on the right track",
    "is this the right approach",
    # General homework vocabulary.
    "my homework assignment",
    "my math homework",
    "my physics homework",
    "my chemistry homework",
    "my biology homework",
    "my english homework",
    "my history homework",
    "my essay i need to write",
    "my lab report",
    "my study guide",
    "my worksheet",
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
