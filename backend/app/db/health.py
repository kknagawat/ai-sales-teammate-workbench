from typing import Any

import redis.asyncio as redis
from sqlalchemy import text

from app.core.health import DependencyHealth
from app.db.session import async_session_factory


def _safe_detail(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


async def check_database() -> DependencyHealth:
    try:
        async with async_session_factory() as session:
            await session.execute(text("select 1"))
        return DependencyHealth(status="ok")
    except Exception as exc:
        return DependencyHealth(status="unavailable", detail=_safe_detail(exc))


async def check_redis(redis_url: str) -> DependencyHealth:
    client: redis.Redis[Any] | None = None
    try:
        client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await client.ping()
        return DependencyHealth(status="ok")
    except Exception as exc:
        return DependencyHealth(status="unavailable", detail=_safe_detail(exc))
    finally:
        if client is not None:
            await client.aclose()
