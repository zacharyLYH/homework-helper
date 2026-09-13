"""E2E harness fixtures: one shared live backend + mock LLM server per session.

This lives in ``tests/e2e/`` so it overrides nothing from the parent unit-test
``conftest.py`` (the parent's autouse fixtures are harmless here — this harness
talks to separate OS processes and reads DB files by explicit path).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest

from .harness import Harness, _build_harness


@pytest.fixture(scope="session")
def harness(tmp_path_factory) -> Iterator[Harness]:
    tmp = tmp_path_factory.mktemp("e2e")
    h = _build_harness(tmp)
    try:
        yield h
    finally:
        h.close()


@pytest.fixture(autouse=True)
def _e2e_isolate(harness: Harness) -> Iterator[None]:
    """Isolate each test: empty memory tables + logs + clean mock routes/log."""
    harness.mock_reset()
    harness.wipe_memory()
    harness.wipe_logs()
    yield


@pytest.fixture
async def e2e_client(harness: Harness) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        base_url=harness.base_url, timeout=httpx.Timeout(120.0, connect=10.0)
    ) as c:
        yield c
