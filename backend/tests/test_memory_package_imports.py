from fastapi import APIRouter

from memory import db, jobs, routes, schemas, seed, service
from memory.config import DEFAULT_MEMORY_DB_PATH, REQUIRED_MEMORY_TABLES
from memory.schemas import MemoryRuntimeStatus
from memory.service import enforce_memory_runtime, get_memory_runtime_status


def test_memory_package_entrypoints_are_importable() -> None:
    assert isinstance(REQUIRED_MEMORY_TABLES, tuple)
    assert DEFAULT_MEMORY_DB_PATH.name == "memory.db"
    assert MemoryRuntimeStatus.__name__ == "MemoryRuntimeStatus"
    assert callable(get_memory_runtime_status)
    assert callable(enforce_memory_runtime)


def test_memory_submodules_have_expected_contracts() -> None:
    assert callable(db.missing_required_tables)
    assert callable(jobs.process_pending_jobs)
    assert callable(seed.run_seed)
    assert isinstance(routes.router, APIRouter)
    assert schemas.MemoryRuntimeStatus is MemoryRuntimeStatus
    assert service.get_memory_runtime_status is get_memory_runtime_status
