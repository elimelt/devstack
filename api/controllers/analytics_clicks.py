"""HTTP endpoints for click analytics.

Provides a beacon fallback endpoint for click event ingestion when WebSocket
is unavailable.
"""

import logging
import os
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from api import db

router = APIRouter()

_logger = logging.getLogger("api.analytics.clicks")
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    _handler.setFormatter(_fmt)
    _logger.addHandler(_handler)
_logger.setLevel(logging.INFO if os.getenv("ANALYTICS_DEBUG", "0") == "1" else logging.WARNING)
_logger.propagate = False


class ClickEventsBatchRequest(BaseModel):
    """Request body for POST /analytics/clicks (beacon fallback)."""

    topic: str = Field(default="clicks", description="Analytics topic (should be 'clicks')")
    events: list[dict[str, Any]] = Field(
        default_factory=list, description="Array of click events"
    )


@router.post("/analytics/clicks", status_code=202)
async def receive_click_events(request: Request, body: ClickEventsBatchRequest) -> dict[str, Any]:
    """Receive a batch of click events via HTTP beacon fallback.

    This endpoint is used when the WebSocket connection is unavailable.
    Events are stored in the events table with topic='clicks'.
    """
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
        # Still return 202 to avoid client retries
        return {"accepted": 0, "message": f"Events received but not stored: {e}"}


@router.get("/analytics/clicks")
async def get_click_events(
    start_date: str | None = Query(
        None,
        description="Filter by start date (ISO8601 format)",
    ),
    end_date: str | None = Query(
        None,
        description="Filter by end date (ISO8601 format)",
    ),
    page_path: str | None = Query(
        None,
        description="Filter by page path",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of events to return",
    ),
) -> dict[str, Any]:
    """Retrieve click events with optional filters."""
    try:
        events = await db.fetch_click_events(
            start_date=start_date,
            end_date=end_date,
            page_path=page_path,
            limit=limit,
        )
        return {
            "events": events,
            "count": len(events),
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "page_path": page_path,
                "limit": limit,
            },
        }
    except Exception as e:
        _logger.exception("Failed to fetch click events")
        return {"events": [], "count": 0, "error": str(e)}

