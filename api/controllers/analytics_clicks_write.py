import logging
import os
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from api import db

router = APIRouter()

_logger = logging.getLogger("api.analytics.clicks.write")
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    _handler.setFormatter(_fmt)
    _logger.addHandler(_handler)
_logger.setLevel(logging.INFO if os.getenv("ANALYTICS_DEBUG", "0") == "1" else logging.WARNING)
_logger.propagate = False


class ClickEventsBatchRequest(BaseModel):
    topic: str = Field(default="clicks", description="Analytics topic (should be 'clicks')")
    events: list[dict[str, Any]] = Field(
        default_factory=list, description="Array of click events"
    )


@router.post("/analytics/clicks", status_code=202)
async def receive_click_events(request: Request, body: ClickEventsBatchRequest) -> dict[str, Any]:
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    events = body.events
    if not events:
        return {"accepted": 0, "message": "No events provided"}

    _logger.info(
        "analytics.clicks.receive ip=%s count=%d topic=%s",
        client_ip,
        len(events),
        body.topic,
    )

    try:
        inserted = await db.insert_click_events(events, client_ip)
        return {"accepted": inserted, "message": "Events accepted"}
    except Exception as e:
        _logger.exception("Failed to insert click events")
        return {"accepted": 0, "message": f"Events received but not stored: {e}"}

