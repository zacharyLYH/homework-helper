from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryRuntimeStatus:
    requested: bool
    enabled: bool
    strict_mode: bool
    reason: str
    db_path: str
