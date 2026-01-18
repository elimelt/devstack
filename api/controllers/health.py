from fastapi import APIRouter

from api import state
from api.db.core import get_pool_stats

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    redis_status = "disconnected"
    if state.redis_client:
        try:
            await state.redis_client.ping()
            redis_status = "healthy"
        except Exception:
            redis_status = "unhealthy"

    return {"status": "ok", "redis": redis_status}


@router.get("/health/pools")
async def health_pools() -> dict:
    """Get connection pool status for Redis and PostgreSQL."""
    # Redis pool stats
    redis_stats = {"status": "not_initialized"}
    if state.redis_client and hasattr(state.redis_client, "connection_pool"):
        pool = state.redis_client.connection_pool
        redis_stats = {
            "max_connections": getattr(pool, "max_connections", None),
            "connection_class": str(type(pool).__name__),
        }

    # PostgreSQL pool stats
    postgres_stats = get_pool_stats()

    return {"redis": redis_stats, "postgres": postgres_stats}
