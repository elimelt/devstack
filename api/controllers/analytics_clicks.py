import logging
import os
from typing import Any

from fastapi import APIRouter, Query

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

