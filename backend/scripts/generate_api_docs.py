"""Generate docs/api.md from the FastAPI app's OpenAPI schema.

Usage (from repo root):
    cd backend && uv run python scripts/generate_api_docs.py
"""
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "api.md"

HTTP_METHODS = ("get", "post", "put", "patch", "delete")

# Endpoint groups: (section title, first path segments). Empty tuple matches
# paths NOT under `/api` (i.e. `/` and `/health`). Ordered by reading order,
# not alphabetical.
SECTIONS: list[tuple[str, tuple[str, ...]]] = [
    ("Health & root", ()),
    ("Subjects", ("api", "subjects")),
    ("Chats", ("api", "chats")),
    ("Chat execution", ("api", "chat")),
    ("Memory", ("api", "memory")),
    ("Settings", ("api", "settings")),
    ("Tools", ("api", "tools")),
    ("Debug (non-prod)", ("api", "debug")),
    ("Auth", ("api", "auth")),
]


def _segments(path: str) -> tuple[str, ...]:
    return tuple(s for s in path.split("/") if s)


def _ref_name(schema: dict[str, Any] | None) -> str:
    """Return a human-readable name for a request-body schema."""
    if not schema:
        return ""
    ref = schema.get("$ref")
    if ref:
        return ref.rsplit("/", 1)[-1]
    for candidate in schema.get("anyOf", []):
        ref = candidate.get("$ref")
        if ref:
            return ref.rsplit("/", 1)[-1]
    return schema.get("title", "")


def _escape(text: str) -> str:
    return text.replace("|", "\\|")


def _rows_for(spec: dict[str, Any], prefix: tuple[str, ...]) -> list[str]:
    """Build markdown table rows for every operation whose path matches prefix.

    A non-empty prefix must match the path's leading segments exactly
    (`("api", "chat")` matches `/api/chat/stream` but not `/api/chats`).
    An empty prefix matches any path whose first segment is not `api`.
    """
    rows: list[str] = []
    for path in sorted(spec["paths"]):
        segs = _segments(path)
        if prefix:
            if segs[0 : len(prefix)] != prefix:
                continue
        elif segs and segs[0] == "api":
            continue
        for method in HTTP_METHODS:
            op = spec["paths"][path].get(method)
            if not op:
                continue
            body_schema = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            body = _ref_name(body_schema)
            summary = _escape(op.get("summary", ""))
            body_col = f"`{body}`" if body else ""
            rows.append(
                f"| `{method.upper()}` | `{_escape(path)}` | {summary} | {body_col} |"
            )
    return rows


def generate() -> str:
    spec = app.openapi()
    lines: list[str] = [
        "# API Reference",
        "",
        "_This file is generated from the FastAPI OpenAPI schema. Do not edit by hand._",
        "",
        "Regenerate with:",
        "",
        "```bash",
        "cd backend && uv run python scripts/generate_api_docs.py",
        "```",
        "",
        "## Authentication",
        "",
        "All endpoints except `/` and `/health` require a valid JWT. It is sent as an",
        "`httpOnly` cookie named `jwt_token` (set on login) or as an",
        "`Authorization: Bearer <token>` header. The JWT claims are `sub`, `email`, `iat`, `exp`.",
        "",
        "## Endpoints",
        "",
    ]

    for title, prefix in SECTIONS:
        rows = _rows_for(spec, prefix)
        if not rows:
            continue
        lines.append(f"### {title}")
        lines.append("")
        lines.append("| Method | Path | Summary | Request body |")
        lines.append("|---|---|---|---|")
        lines.extend(rows)
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(generate(), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()