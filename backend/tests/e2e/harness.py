"""E2E harness: boots real backend + memory worker + mock-LLM server.

The harness owns three OS processes and a set of temp DB files:

  * mock LLM server  - ``tests/e2e/mock_llm.py`` (scriptable, real HTTP)
  * backend          - ``uvicorn app.main:app`` on a random port
  * memory worker    - ``python -m memory.jobs`` polling loop (its own process,
    exactly like production; the backend only enqueues jobs into the DB)

Tests never crank the worker manually: they chat over HTTP, script what the
worker's LLM should say per turn via :meth:`Harness.mock_route`, and wait for
jobs to drain with :meth:`Harness.wait_jobs_done` (an **absolute** count of
terminal jobs — the worker runs continuously, so relative counting races).

This module has no pytest imports so it stays framework-agnostic (pure escaping
hatch for ``conftest.py`` to build fixtures on).
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx


def memory_eval(
    *,
    observations: list[str] | None = None,
    concept_upserts: list[dict] | None = None,
    concept_edges: list[dict] | None = None,
    concept_state_deltas: list[dict] | None = None,
    trait_updates: dict[str, str] | None = None,
    updated_summary: str = "",
) -> dict:
    """Build a producing MemoryEvaluation payload (mirror of the LLM schema)."""
    return {
        "skip": False,
        "observations": observations or [],
        "concept_upserts": concept_upserts or [],
        "concept_edges": concept_edges or [],
        "concept_state_deltas": concept_state_deltas or [],
        "trait_updates": trait_updates or {},
        "updated_summary": updated_summary,
    }


def skip_eval() -> dict:
    """A memory evaluation that marks a job done without writing rows."""
    return {
        "skip": True,
        "observations": [],
        "concept_upserts": [],
        "concept_edges": [],
        "concept_state_deltas": [],
        "trait_updates": {},
        "updated_summary": "",
    }


BACKEND_DIR = Path(__file__).resolve().parents[2]
MOCK_LLM_PATH = Path(__file__).resolve().parent / "mock_llm.py"

LLM_CONFIG = {
    "version": 1,
    "name": "e2e",
    "triplets": [
        {"alias": "mock", "provider": "openrouter", "model": "openrouter/free",
         "api_key": "sk-test-key", "has_key": True}
    ],
    "chat": {"order": ["mock"], "rules": []},
    "memory": {"order": ["mock"], "rules": []},
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_http(url: str) -> None:
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=1.0).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise TimeoutError(f"Endpoint did not become ready: {url}")


@dataclass
class Harness:
    """Everything a test needs to drive the live backend + worker organically."""

    HTTP_TIMEOUT = 30.0

    base_url: str
    mock_url: str
    app_db: Path
    debug_db: Path
    memory_db: Path
    backend_proc: subprocess.Popen
    mock_proc: subprocess.Popen
    worker_proc: subprocess.Popen
    worker_log: Path
    backend_log: Path
    env: dict[str, str]
    tmp_dir: Path
    _mock: httpx.Client = field(default=None, init=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._mock = httpx.Client(base_url=self.mock_url, timeout=self.HTTP_TIMEOUT)

    # ------------------------------------------------------------------ DB ---
    def sql(self, db: str, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        path = {"app": self.app_db, "debug": self.debug_db, "memory": self.memory_db}[db]
        conn = sqlite3.connect(str(path))
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            conn.commit()  # no-op for reads, required for seeded writes
            return rows
        finally:
            conn.close()

    def memory_count(self, table: str) -> int:
        return int(self.sql("memory", f"SELECT COUNT(*) FROM {table}")[0][0])

    def enqueue_reasons(self) -> list[str]:
        """All memory-updater enqueue decisions from the structured logs.

        The debug DB holds one ``memory_enqueue_decision`` event per turn with
        ``enqueued``/``reason`` — ground truth for the skip heuristics.
        """
        rows = self.sql(
            "debug",
            "SELECT log FROM structured_logs WHERE type = 'memory_enqueue_decision' ORDER BY id",
        )
        return [str(json.loads(r["log"]).get("reason")) for r in rows]

    def wait_enqueue_reasons(self, total: int) -> list[str]:
        """Wait until ``total`` enqueue decisions are committed, then return them.

        The middleware commits a request's structured log after the last SSE
        byte is sent, so a test reading immediately after ``chat_turn`` can
        miss the decision that was just made.
        """
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            reasons = self.enqueue_reasons()
            if len(reasons) >= total:
                return reasons
            time.sleep(0.1)
        raise AssertionError(
            f"timed out waiting for {total} enqueue decisions (have {self.enqueue_reasons()})"
        )

    def job_statuses(self) -> list[str]:
        """All memory-job statuses in creation order."""
        return [
            r["status"]
            for r in self.sql("memory", "SELECT status FROM memory_update_jobs ORDER BY id")
        ]

    def wipe_memory(self) -> None:
        """Empty every memory table — used between tests sharing one harness."""
        tables = (
            "retrieval_traces", "memory_update_jobs", "memory_summary",
            "learner_traits", "learner_concept_state", "learner_observations",
            "concept_edges", "concepts",
        )
        conn = sqlite3.connect(str(self.memory_db))
        try:
            conn.executescript("".join(f"DELETE FROM {t};" for t in tables))
            conn.commit()
        finally:
            conn.close()

    def wipe_logs(self) -> None:
        """Empty the structured-log table — the debug DB is session-scoped."""
        self.sql("debug", "DELETE FROM structured_logs")

    # ------------------------------------------------------------ mock llm ---
    def mock_reset(self) -> None:
        r = self._mock.post("/__control/reset")
        r.raise_for_status()

    def mock_calls(self) -> list[dict]:
        r = self._mock.get("/__control/log")
        r.raise_for_status()
        return r.json()

    def chat_calls(self) -> list[dict]:
        """Chat-completion calls only (evals/title-gen are non-streaming).

        The background worker's eval calls land in the log concurrently with
        chat turns, so tests asserting on "the last chat call" must filter —
        ``mock_calls()[-1]`` is ambiguous under a live worker.
        """
        return [c for c in self.mock_calls() if c["stream"]]

    def eval_calls(self) -> list[dict]:
        """Memory-eval calls received by the mock (non-streaming)."""
        return [c for c in self.mock_calls() if not c["stream"]]

    def wait_eval_calls(self, total: int) -> list[dict]:
        """Wait until the mock has received ``total`` eval requests.

        The mock logs a request when it arrives (before honoring any
        ``delay_ms``), so this is the deterministic signal that a worker is
        mid-eval with the response being held — e.g. the safe moment to kill
        the worker in crash tests.
        """
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            calls = self.eval_calls()
            if len(calls) >= total:
                return calls
            time.sleep(0.05)
        raise AssertionError(f"timed out waiting for {total} eval calls")

    def mock_route(self, specs: dict | list[dict]) -> None:
        """Register content-routed memory-evaluation specs.

        Each spec needs a ``match`` substring of the turn text; the mock LLM
        serves the spec's payload for the eval request whose prompt contains
        that substring. A spec serves ``times`` attempts (default one-shot).
        Register BEFORE the turn that enqueues the matching job — the worker
        may claim it the instant it is enqueued.
        """
        specs = specs if isinstance(specs, list) else [specs]
        for s in specs:
            assert "match" in s, "routed spec needs a 'match' substring"
        r = self._mock.post("/__control/route", json=specs)
        r.raise_for_status()

    # ----------------------------------------------------------------- auth --
    def register_user(self, email: str) -> str:
        """Register a user and complete the real email-code flow.

        SMTP is not configured, so the backend skips the network send and logs
        the code; we read it straight from the app DB (same file it uses).
        """
        # No register endpoint exists: users are seeded into the app DB, then
        # the real request-code -> verify flow runs over HTTP.
        self.sql("app", "INSERT OR IGNORE INTO users (email) VALUES (?)", (email,))
        with httpx.Client(base_url=self.base_url, timeout=self.HTTP_TIMEOUT) as c:
            c.post("/api/auth/request-code", json={"email": email}).raise_for_status()
        row = self.sql(
            "app", "SELECT code FROM verification_codes WHERE email = ? ORDER BY id DESC", (email,)
        )[0]
        with httpx.Client(base_url=self.base_url, timeout=self.HTTP_TIMEOUT) as c:
            v = c.post("/api/auth/verify", json={"email": email, "code": row["code"]})
            v.raise_for_status()
        return str(v.json()["access_token"])

    def seed_llm_config(self, token: str) -> None:
        with httpx.Client(base_url=self.base_url, timeout=self.HTTP_TIMEOUT) as c:
            r = c.put(
                "/api/settings/config",
                json=LLM_CONFIG,
                headers=self.auth(token),
            )
            r.raise_for_status()

    @staticmethod
    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    # --------------------------------------------------------------- worker --
    def wait_jobs_done(self, total: int) -> list[str]:
        """Wait until at least ``total`` jobs have reached a terminal status.

        Absolute, not delta-based: the background worker claims and finishes
        jobs concurrently with the test, so counting "N more since now" races
        (a job can finish before the baseline is taken). Returns the full
        status list (job-id order) for assertions about which statuses exist.
        Fails with the worker's and backend's recent logs on timeout.
        """
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            current = self.job_statuses()
            if sum(s in ("done", "failed") for s in current) >= total:
                return current
            time.sleep(0.2)
        raise AssertionError(
            f"timed out waiting for {total} jobs to be terminal "
            f"(statuses={self.job_statuses()})"
            f"\nworker log tail:\n{self.worker_log_tail()}"
            f"\nbackend log tail:\n{self.backend_log_tail()}"
        )

    def worker_log_tail(self, lines: int = 15) -> str:
        try:
            content = self.worker_log.read_text()
        except OSError:
            return "(no worker log)"
        return "\n".join(content.splitlines()[-lines:])

    def backend_log_tail(self, lines: int = 30) -> str:
        try:
            content = self.backend_log.read_text()
        except OSError:
            return "(no backend log)"
        return "\n".join(content.splitlines()[-lines:])

    def restart_worker(self) -> None:
        """SIGKILL the worker mid-flight and boot a fresh one (simulated crash)."""
        if self.worker_proc.poll() is None:
            self.worker_proc.kill()
            self.worker_proc.wait(timeout=10)
        self.worker_proc, self.worker_log = _spawn_worker(self.env, self.tmp_dir)

    # ------------------------------------------------------------- teardown --
    def close(self) -> None:
        for proc in (self.worker_proc, self.backend_proc, self.mock_proc):
            if proc.poll() is None:
                proc.terminate()
        for proc in (self.worker_proc, self.backend_proc, self.mock_proc):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._mock.close()


def _build_harness(tmp_dir: Path) -> Harness:
    """Start the mock LLM server and the backend; poll until both are ready."""
    mock_port = _free_port()
    backend_port = _free_port()
    mock_url = f"http://127.0.0.1:{mock_port}"
    base_url = f"http://127.0.0.1:{backend_port}"

    app_db = tmp_dir / "homework_helper.db"
    debug_db = tmp_dir / "debug.db"
    memory_db = tmp_dir / "memory.db"
    debug_db.touch()

    env = {
        **os.environ,
        "ENVIRONMENT": "test",
        "DATABASE_PATH": str(app_db),
        "DEBUG_DATABASE_PATH": str(debug_db),
        "MEMORY_DATABASE_PATH": str(memory_db),
        "MEMORY_ENABLED": "true",
        # Worker-side LLM timeout, shrunk from the 90s default so the timeout
        # fault is testable via the mock's delay_ms. Only the worker's
        # evaluate_memory reads this; the backend never does.
        "MEMORY_LLM_TIMEOUT_SECONDS": "3",
        # Stale-job reclaim, shrunk from the 300s default so a worker-crash
        # test reclaims quickly. Safety margin: the longest legit eval here is
        # the 3s LLM timeout above, so a live 'running' job is never stolen.
        "MEMORY_STALE_JOB_SECONDS": "5",
        "JWT_SECRET_KEY": "e2e-secret-key",
        "AES_SECRET_KEY": "e2e-aes-secret-key-0123456789abcdef",
        "OPENROUTER_API_KEY": "sk-e2e",
        "STRUCTURED_LOGGING_PCT": "100",
        "PROVIDER_BASE_URL_OVERRIDE": f"{mock_url}/v1",
        # Keep the backend hermetically off the network: no real SMTP, no real
        # model provider. Overrides any development .env the host may have.
        "SMTP_USER": "",
        "SMTP_PASSWORD": "",
        "OPENROUTER_BASE_URL": f"{mock_url}/v1",
    }

    # 1. Boot the mock LLM server first (the backend will point at it).
    mock_proc = subprocess.Popen(
        [sys.executable, str(MOCK_LLM_PATH), "--port", str(mock_port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_http(f"{mock_url}/__control/health")

    # 2. Create the memory schema before the backend boots (strict mode refuses
    # to serve without it). A one-shot worker run does the init and exits.
    worker_init = subprocess.run(
        [sys.executable, "-m", "memory.jobs", "--once"],
        cwd=str(BACKEND_DIR),
        env={**env},
        capture_output=True,
        text=True,
        timeout=120,
    )
    if worker_init.returncode != 0:
        raise RuntimeError(f"worker schema init failed: {worker_init.stderr}")

    # 3. Boot the backend (stderr captured for post-mortem debugging).
    backend_log = tmp_dir / "backend.log"
    with backend_log.open("w") as log_fh:
        backend_proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "app.main:app",
                "--host", "127.0.0.1", "--port", str(backend_port), "--log-level", "warning",
            ],
            cwd=str(BACKEND_DIR),
            env={**env},
            stdout=subprocess.DEVNULL,
            stderr=log_fh,
        )
    _wait_for_http(f"{base_url}/health")

    # 4. Boot the real memory worker loop as its own process (production shape:
    # the backend only enqueues; the worker polls the queue independently).
    worker_proc, worker_log = _spawn_worker(env, tmp_dir)

    return Harness(
        base_url=base_url,
        mock_url=mock_url,
        app_db=app_db,
        debug_db=debug_db,
        memory_db=memory_db,
        backend_proc=backend_proc,
        mock_proc=mock_proc,
        worker_proc=worker_proc,
        worker_log=worker_log,
        backend_log=backend_log,
        env=env,
        tmp_dir=tmp_dir,
    )


def _spawn_worker(env: dict[str, str], tmp_dir: Path) -> tuple[subprocess.Popen, Path]:
    """Start the memory worker loop; its log accumulates across restarts."""
    worker_log = tmp_dir / "worker.log"
    with worker_log.open("a") as log_fh:
        worker_proc = subprocess.Popen(
            [sys.executable, "-m", "memory.jobs", "--poll-interval", "0.5"],
            cwd=str(BACKEND_DIR),
            env={**env},
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )
    return worker_proc, worker_log


# --------------------------------------------------------------------- flow ---
# Intent-level helpers tests compose into multi-turn flows over real HTTP.


async def create_subject(client: httpx.AsyncClient, token: str, name: str) -> int:
    r = await client.post("/api/subjects", params={"name": name}, headers=Harness.auth(token))
    r.raise_for_status()
    return int(r.json()["id"])


async def create_chat(client: httpx.AsyncClient, token: str, subject_id: int) -> int:
    # Explicit non-default title: the backend only fires a title-generation LLM
    # call for chats still named "New Chat", and that extra call adds noise.
    r = await client.post(
        "/api/chats",
        params={"subject_id": subject_id, "title": "Prefilled"},
        headers=Harness.auth(token),
    )
    r.raise_for_status()
    return int(r.json()["id"])


async def chat_turn(
    client: httpx.AsyncClient, token: str, chat_id: int, message: str
) -> str:
    """Send one chat turn; the backend streams the mock LLM's default reply."""
    text: list[str] = []
    async with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": message, "chat_id": chat_id},
        headers=Harness.auth(token),
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[len("data: ") :]
            if payload == "[DONE]":
                continue
            event = json.loads(payload)
            if event.get("type") == "token":
                text.append(event.get("content", ""))
    return "".join(text)
