from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.health import DependencyHealth
from app.core.runtime_config import get_effective_settings
from app.db.health import check_database, check_redis

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    api: str
    db: DependencyHealth
    redis: DependencyHealth
    llm: DependencyHealth


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    settings = get_settings()
    effective_settings = get_effective_settings(settings)
    db = await check_database()
    redis = await check_redis(settings.redis_url)
    llm = effective_settings.llm_health()

    dependency_statuses = (db.status, redis.status, llm.status)
    overall = "ok" if all(status == "ok" for status in dependency_statuses) else "degraded"
    return HealthResponse(status=overall, api="ok", db=db, redis=redis, llm=llm)
