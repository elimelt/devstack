from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from api import state


class CacheValue(BaseModel):
    value: str
    ttl: int | None = 3600


router = APIRouter()


@router.post("/cache/{key}")
async def set_cache(key: str, data: CacheValue) -> dict[str, Any]:
    if not state.redis_client:
        return {"error": "Redis not connected"}

    await state.redis_client.setex(key, data.ttl, data.value)
    return {"key": key, "value": data.value, "ttl": data.ttl, "success": True}

