from .admin import router as admin_router
from .auth_routes import router as auth_router
from .data import router as data_router

__all__ = ["auth_router", "data_router", "admin_router"]
