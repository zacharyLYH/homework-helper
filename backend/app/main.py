from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.logging import get_logger
from app.routes import api_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting homework-helper backend")
    init_db()
    yield
    log.info("Shutting down homework-helper backend")


app = FastAPI(title="homework-helper-backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:80", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
