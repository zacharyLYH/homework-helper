"""Pre-download the embedding model into the repo so it ships inside the Docker image.

Usage:
    uv run python scripts/download_embedding_model.py
    uv run python scripts/download_embedding_model.py <repo-id>
"""
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# SentenceTransformer only needs the torch/weights + tokenizer files. Skip the
# onnx/openvino/tf/rust exports to keep the repo small.
IGNORE_PATTERNS = [
    "*.h5",
    "*.ot",
    "*.onnx",
    "*.xml",
    "*.bin",
    "*.ckpt",
    "*.pb",
    "*.gguf",
    "onnx/*",
    "openvino/*",
    "README.md",
    "train_script.py",
]


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    dest = Path(__file__).resolve().parent.parent / "models" / name
    dest.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=name, local_dir=dest, ignore_patterns=IGNORE_PATTERNS)
    print(f"Downloaded {name} to {dest}")


if __name__ == "__main__":
    main()
