import sqlite3
from pathlib import Path

from memory.config import REQUIRED_MEMORY_TABLES


def missing_required_tables(db_path: Path) -> list[str]:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

    table_names = {row[0] for row in rows}
    return [table for table in REQUIRED_MEMORY_TABLES if table not in table_names]
