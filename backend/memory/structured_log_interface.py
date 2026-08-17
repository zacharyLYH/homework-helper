"""Memory-specific bridge for structured-log trace propagation."""

import contextvars as cv
from types import TracebackType
from typing import Literal

import app.structured_log as structured_log_module


def get_enqueue_trace_id() -> str | None:
    """Return the active request trace ID for a queued memory job."""
    logger = structured_log_module.get_structured_logger()
    return logger._req_id if logger is not None else None


class MemoryJobLogContext:
    """Emit and commit a worker job's logs under its originating trace ID."""

    def __init__(self, trace_id: str | None) -> None:
        self._trace_id = trace_id
        self._logger: structured_log_module.StructuredLogger | None = None
        self._token: cv.Token[structured_log_module.StructuredLogger | None] | None = None

    def __enter__(self) -> None:
        logger = structured_log_module.StructuredLogger(should_commit=True)
        if self._trace_id is not None:
            logger._req_id = self._trace_id
        self._logger = logger
        self._token = structured_log_module._logger_var.set(logger)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        assert self._logger is not None
        assert self._token is not None
        try:
            self._logger.commit()
        finally:
            structured_log_module._logger_var.reset(self._token)
        return False


def memory_job_log_context(trace_id: str | None) -> MemoryJobLogContext:
    """Create a structured-log context for a memory worker job."""
    return MemoryJobLogContext(trace_id)