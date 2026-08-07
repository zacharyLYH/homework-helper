"""Request-scoped structured tracing.

Each request gets a logger that buffers every `structured_log` event. The ASGI
middleware wraps the app and, at the end, commits the whole trace as one unit
(discarding it otherwise) based on a single bool that is sampled up front or
forced to True mid-request. A request is never partially logged.
"""
import contextvars as cv
import json
import random
import uuid
from datetime import datetime, timezone
from typing import Any

_logger_var: cv.ContextVar["StructuredLogger | None"] = cv.ContextVar("structured_logger", default=None)


class StructuredLogger:
    def __init__(self, should_commit: bool) -> None:
        self.should_commit = should_commit
        self.message_id: int | None = None
        self._req_id = uuid.uuid4().hex
        self._entries: list[dict] = []

    def log(self, type: str, **data: Any) -> None:
        self._entries.append({
            "type": type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message_id": self.message_id,
            "log": json.dumps(data, ensure_ascii=False, default=str),
        })

    def set_message_id(self, message_id: int) -> None:
        self.message_id = message_id

    def commit(self) -> None:
        if not self.should_commit or not self._entries:
            return
        from app.db import insert_structured_logs_batch

        insert_structured_logs_batch([
            (e["type"], e["created_at"], self.message_id, e["log"], self._req_id)
            for e in self._entries
        ])
        self._entries.clear()


def structured_log(type: str, **data: Any) -> None:
    logger = _logger_var.get()
    if logger is not None:
        logger.log(type, **data)


def get_structured_logger() -> StructuredLogger | None:
    return _logger_var.get()


def force_structured_logger() -> None:
    """Commit the current request trace regardless of sampling."""
    logger = _logger_var.get()
    if logger is None:
        logger = StructuredLogger(should_commit=True)
        _logger_var.set(logger)
    else:
        logger.should_commit = True


class StructuredTraceMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from app.config import settings

        token = _logger_var.set(StructuredLogger(should_commit=random.randint(1, 100) <= settings.structured_logging_pct))
        try:
            await self.app(scope, receive, send)
        finally:
            logger = _logger_var.get()
            try:
                if logger is not None:
                    logger.commit()
            finally:
                _logger_var.reset(token)