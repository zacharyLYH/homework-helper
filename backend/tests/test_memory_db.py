from app.db import get_conn as get_app_conn
from memory import db as memory_db
from memory.config import REQUIRED_MEMORY_TABLES


def test_memory_schema_bootstrap_creates_required_tables(tmp_path) -> None:
    memory_db_path = tmp_path / "memory.db"

    created_path = memory_db.init_db(memory_db_path)

    assert created_path == memory_db_path
    assert memory_db_path.exists()
    assert memory_db.missing_required_tables(memory_db_path) == []


def test_memory_tables_absent_from_main_app_db(setup_test_db) -> None:
    with get_app_conn() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

    app_tables = {row[0] for row in rows}
    assert not app_tables.intersection(REQUIRED_MEMORY_TABLES)


def test_memory_db_crud_smoke(tmp_path) -> None:
    memory_db_path = tmp_path / "memory.db"
    memory_db.init_db(memory_db_path)

    with memory_db.get_conn(memory_db_path) as conn:
        concept_cur = conn.execute(
            "INSERT INTO concepts (subject_id, concept_key, display_name) VALUES (?, ?, ?)",
            (1, "quadratic_formula", "Quadratic Formula"),
        )
        concept_id = concept_cur.lastrowid
        assert concept_id is not None

        obs_cur = conn.execute(
            """
            INSERT INTO learner_observations (user_id, subject_id, observation, source)
            VALUES (?, ?, ?, ?)
            """,
            (1, 42, "Learner misapplies sign when using b^2 - 4ac", "chat"),
        )
        observation_id = obs_cur.lastrowid
        assert observation_id is not None

        row = conn.execute(
            "SELECT concept_key, display_name FROM concepts WHERE id = ?",
            (concept_id,),
        ).fetchone()
        assert row is not None
        assert row["concept_key"] == "quadratic_formula"

        conn.execute(
            "UPDATE learner_observations SET observation = ? WHERE id = ?",
            ("Learner correctly applies discriminant", observation_id),
        )

        updated = conn.execute(
            "SELECT observation FROM learner_observations WHERE id = ?",
            (observation_id,),
        ).fetchone()
        assert updated is not None
        assert updated["observation"] == "Learner correctly applies discriminant"

        conn.execute(
            "DELETE FROM learner_observations WHERE id = ?",
            (observation_id,),
        )

        remaining = conn.execute(
            "SELECT COUNT(*) FROM learner_observations WHERE id = ?",
            (observation_id,),
        ).fetchone()
        assert remaining is not None
        assert remaining[0] == 0
