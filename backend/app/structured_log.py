import contextvars
import json
import random
import uuid
from datetime import datetime, timezone
from typing import Any

_logger_var: contextvars.ContextVar["StructuredLogger | None"] = contextvars.ContextVar("structured_logger", default=None)


class StructuredLogger:
    def __init__(self) -> None:
        self.active = True
        self.message_id: int | None = None
        self._req_id: str = uuid.uuid4().hex

    def log(self, type: str, **data: Any) -> None:
        if not self.active:
            return
        from app.db import insert_structured_log

        insert_structured_log(
            type=type,
            created_at=datetime.now(timezone.utc).isoformat(),
            message_id=self.message_id,
            log=json.dumps(data, ensure_ascii=False, default=str),
            req_id=self._req_id,
        )

    def set_message_id(self, message_id: int) -> None:
        self.message_id = message_id
        from app.db import update_structured_log_message_id

        update_structured_log_message_id(self._req_id, message_id)


def roll_dice(pct: int) -> bool:
    return random.randint(1, 100) <= pct


def init_structured_logger(pct: int) -> StructuredLogger | None:
    if roll_dice(pct):
        logger = StructuredLogger()
        _logger_var.set(logger)
        return logger
    return None


def force_structured_logger() -> StructuredLogger:
    """Create and set a structured logger regardless of sampling.

    Used for events that must always be observable (e.g. rejected requests).
    """
    logger = StructuredLogger()
    _logger_var.set(logger)
    return logger


def get_structured_logger() -> StructuredLogger | None:
    return _logger_var.get()


def structured_log(type: str, **data: Any) -> None:
    logger = get_structured_logger()
    if logger is not None:
        logger.log(type, **data)
