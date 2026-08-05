from __future__ import annotations

import argparse
from pathlib import Path

from app.logging import get_logger
from memory.db import get_conn, init_db

log = get_logger(__name__)

DEFAULT_SEED_SQL_PATH = (
    Path(__file__).parent.parent.parent / "data" / "memory-seed.sql"
).resolve()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed the standalone memory database")
    parser.add_argument(
        "--seed-sql-path",
        type=str,
        default=str(DEFAULT_SEED_SQL_PATH),
        help="Path to SQL seed file",
    )
    return parser


def run_seed(*, seed_sql_path: Path) -> Path:
    db_path = init_db()

    if not seed_sql_path.exists():
        raise FileNotFoundError(f"Seed SQL file not found: {seed_sql_path}")

    seed_sql = seed_sql_path.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.executescript(seed_sql)

    return db_path


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    seed_path = Path(args.seed_sql_path).resolve()
    db_path = run_seed(seed_sql_path=seed_path)
    log.info("Memory seed complete: db=%s seed=%s", db_path, seed_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
