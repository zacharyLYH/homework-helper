import pytest

from memory import db as memory_db
from memory.service.main import enforce_memory_runtime, get_memory_runtime_status


def test_memory_runtime_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", tmp_path / "memory.db")
    status = get_memory_runtime_status(
        memory_enabled=False,
        memory_strict_mode=True,
    )

    assert status.requested is False
    assert status.enabled is False
    assert status.reason == "disabled_by_config"


def test_memory_runtime_missing_db_auto_disables_when_not_strict(tmp_path, monkeypatch):
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", tmp_path / "missing-memory.db")
    status = get_memory_runtime_status(
        memory_enabled=True,
        memory_strict_mode=False,
    )

    assert status.requested is True
    assert status.enabled is False
    assert status.reason == "memory_db_missing"



def test_memory_runtime_missing_db_raises_when_strict(tmp_path, monkeypatch):
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", tmp_path / "missing-memory.db")
    status = get_memory_runtime_status(
        memory_enabled=True,
        memory_strict_mode=True,
    )

    with pytest.raises(RuntimeError):
        enforce_memory_runtime(status)


def test_memory_runtime_enabled_when_schema_exists(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    memory_db.init_db(db_path)
    monkeypatch.setattr("memory.config.DEFAULT_MEMORY_DB_PATH", db_path)

    status = get_memory_runtime_status(
        memory_enabled=True,
        memory_strict_mode=True,
    )

    assert status.requested is True
    assert status.enabled is True
    assert status.reason == "memory_enabled"

    # Should not raise when memory is fully available.
    enforce_memory_runtime(status)
