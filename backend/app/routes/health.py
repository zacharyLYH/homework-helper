from fastapi import APIRouter

from app.config import settings
from app.graph import compiled_graph
from app.schemas import HealthResponse

router = APIRouter()


@router.get("/", response_model=dict)
async def root():
    return {"service": "homework-helper-backend", "docs": "/docs"}


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        model=settings.openrouter_model,
        graph_compiled=compiled_graph is not None,
    )
