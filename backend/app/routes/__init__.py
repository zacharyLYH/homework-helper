from fastapi import APIRouter

from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.debug import router as debug_router
from app.routes.health import router as health_router
from app.routes.tools import router as tools_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(health_router)
api_router.include_router(chat_router)
api_router.include_router(tools_router)
api_router.include_router(debug_router)
