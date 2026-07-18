from fastapi import APIRouter

from app.schemas import ToolInfo
from app.tools import ALL_TOOLS

router = APIRouter()


@router.get("/api/tools", response_model=list[ToolInfo])
async def list_tools():
    return [ToolInfo(name=t.name, description=t.description) for t in ALL_TOOLS]
