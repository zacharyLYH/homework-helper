"""Encryption of stored API keys.

Keys are encrypted at rest with AES-256 (via Fernet, i.e. AES-CBC + HMAC) and
decrypted only immediately before an LLM call. The Fernet key is derived from
``AES_SECRET_KEY``. If that setting is missing, every encrypt/decrypt raises
``MissingSecretKeyError`` so we never silently store or use plaintext keys.
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

MASK_PREFIX_LEN = 4
MASK_SUFFIX_LEN = 4


class MissingSecretKeyError(RuntimeError):
    """Raised when AES_SECRET_KEY is not configured."""


def _derive_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    secret = settings.aes_secret_key
    if not secret:
        raise MissingSecretKeyError(
            "AES_SECRET_KEY is not set. Refusing to encrypt/decrypt API keys."
        )
    return Fernet(_derive_key(secret))


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Stored API key could not be decrypted") from exc


def mask_key(key: str) -> str:
    """Human-friendly mask: ``sk-abcd****wxyz``. Empty keys stay empty."""
    if not key:
        return ""
    if len(key) <= MASK_PREFIX_LEN + MASK_SUFFIX_LEN:
        return "****"
    return f"{key[:MASK_PREFIX_LEN]}****{key[-MASK_SUFFIX_LEN:]}"


def decrypt_safe(token: str) -> str | None:
    """Return the plaintext key, or ``None`` when the token is unusable."""
    if not token:
        return None
    try:
        return decrypt(token)
    except ValueError:
        return None
