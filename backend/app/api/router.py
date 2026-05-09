from fastapi import APIRouter

from app.api.routes import auth, config, health, work_items

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(work_items.router, tags=["work-items"])
api_router.include_router(work_items.admin_router, tags=["admin"])
