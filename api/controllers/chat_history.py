from typing import Any

from fastapi import APIRouter, Query

from api import db

router = APIRouter()


@router.get("/chat/{channel}/history")
async def chat_history(
    channel: str,
    before: str | None = Query(None, description="ISO8601 timestamp; default now"),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    messages = await db.fetch_chat_history(channel, before, limit)
    next_before = messages[-1]["timestamp"] if messages else before
    return {"messages": messages, "next_before": next_before}
