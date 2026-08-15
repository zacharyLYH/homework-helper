from fastapi import APIRouter, Request

from app.config import settings
from app.graph import compiled_graph
from app.schemas import HealthResponse, RootResponse

router = APIRouter()


@router.get("/", response_model=RootResponse)
async def root() -> RootResponse:
    return RootResponse(service="homework-helper-backend", docs="/docs")


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        model=settings.openrouter_model,
        graph_compiled=compiled_graph is not None,
        memory_enabled=bool(getattr(request.app.state, "memory_enabled", False)),
    )
