from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db, init_debug_db
from app.logging import get_logger
from app.routes import api_router
from memory.service import enforce_memory_runtime, get_memory_runtime_status
from app.structured_log import StructuredTraceMiddleware

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting homework-helper backend")
    init_db()
    init_debug_db()
    memory_status = get_memory_runtime_status(
        memory_enabled=settings.memory_enabled,
        memory_strict_mode=settings.memory_strict_mode,
    )
    log.info(
        "Memory runtime check: requested=%s strict_mode=%s enabled=%s reason=%s",
        memory_status.requested,
        memory_status.strict_mode,
        memory_status.enabled,
        memory_status.reason,
    )
    enforce_memory_runtime(memory_status)
    if memory_status.enabled:
        log.info("Memory runtime enabled: db=%s", memory_status.db_path)
        log.info("Manual flow mode: MEMORY ON (loader/injection/updater active)")
    else:
        log.warning(
            "Memory runtime disabled: requested=%s reason=%s db=%s",
            memory_status.requested,
            memory_status.reason,
            memory_status.db_path,
        )
        log.info("Manual flow mode: MEMORY OFF (regular chat flow continues without memory hooks)")
    app.state.memory_enabled = memory_status.enabled
    app.state.memory_status_reason = memory_status.reason
    yield
    log.info("Shutting down homework-helper backend")


app = FastAPI(title="homework-helper-backend", version="0.1.0", lifespan=lifespan)

# Must wrap the whole app so streaming responses are fully produced (and the
# final log events emitted) before the structured trace is committed/discarded.
app.add_middleware(StructuredTraceMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:80", "http://localhost", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
