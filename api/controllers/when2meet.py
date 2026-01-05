import logging
from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException

from api import db

logger = logging.getLogger("api.when2meet")
router = APIRouter()


@router.get("/events/{event_id}")
async def get_event(event_id: str) -> dict[str, Any]:
    logger.info("GET /events/%s", event_id)
    event = await db.w2m_get_event(event_id)
    if not event:
        logger.warning("Event not found: %s", event_id)
        raise HTTPException(status_code=404, detail="Event not found")
    availabilities = await db.w2m_get_availabilities(event_id)
    slot_counts: Counter = Counter()
    for a in availabilities:
        for slot in a["available_slots"]:
            slot_counts[slot] += 1
    logger.info("Returning event %s with %d availabilities", event_id, len(availabilities))
    return {
        "event": event,
        "availabilities": availabilities,
        "summary": dict(slot_counts),
    }