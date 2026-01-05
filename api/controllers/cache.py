from typing import Any

from fastapi import APIRouter

from api import state

router = APIRouter()


@router.get("/cache/{key}")
async def get_cache(key: str) -> dict[str, Any]:
    if not state.redis_client:
        return {"error": "Redis not connected"}

    value = await state.redis_client.get(key)
    if value is None:
        return {"key": key, "value": None, "found": False}

    return {"key": key, "value": value, "found": True}
