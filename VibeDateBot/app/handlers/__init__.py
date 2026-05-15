from app.handlers.admin import router as admin_router
from app.handlers.common import router as common_router
from app.handlers.dating import router as dating_router

__all__ = ["admin_router", "common_router", "dating_router"]
