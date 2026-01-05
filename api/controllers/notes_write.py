import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from api import db
from api.notes_sync import sync_notes_with_job, retry_failed_items

router = APIRouter(prefix="/notes", tags=["notes"])

NOTES_SYNC_SECRET = os.getenv("NOTES_SYNC_SECRET", "")


def _validate_sync_secret(x_sync_secret: str | None) -> None:
    if not NOTES_SYNC_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Sync endpoint not configured (NOTES_SYNC_SECRET not set)",
        )
    if x_sync_secret != NOTES_SYNC_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing sync secret")


@router.post("/sync")
async def trigger_sync(
    force: bool = Query(False, description="Force sync even if already at latest commit"),
    x_sync_secret: str | None = Header(None, alias="X-Sync-Secret"),
) -> dict[str, Any]:
    _validate_sync_secret(x_sync_secret)

    github_token = os.getenv("GITHUB_TOKEN")
    result = await sync_notes_with_job(token=github_token, force=force)

    return result


@router.post("/sync/jobs/{job_id}/resume")
async def resume_sync_job(
    job_id: int,
    x_sync_secret: str | None = Header(None, alias="X-Sync-Secret"),
) -> dict[str, Any]:
    _validate_sync_secret(x_sync_secret)

    job = await db.sync_job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Sync job {job_id} not found")

    if job["status"] not in ("paused", "running", "pending"):
        raise HTTPException(
            status_code=400,
            detail=f"Job cannot be resumed (status: {job['status']})",
        )

    github_token = os.getenv("GITHUB_TOKEN")
    result = await sync_notes_with_job(token=github_token, resume_job_id=job_id)

    return result


@router.post("/sync/jobs/{job_id}/retry")
async def retry_failed_job_items(
    job_id: int,
    x_sync_secret: str | None = Header(None, alias="X-Sync-Secret"),
) -> dict[str, Any]:
    _validate_sync_secret(x_sync_secret)

    job = await db.sync_job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Sync job {job_id} not found")

    github_token = os.getenv("GITHUB_TOKEN")
    result = await retry_failed_items(job_id, token=github_token)

    return result


@router.get("/sync/failed-items")
async def list_failed_items(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of items to return"),
    job_id: int | None = Query(None, description="Filter by specific job ID"),
) -> dict[str, Any]:
    items = await db.sync_job_list_all_failed_items(limit=limit, job_id=job_id)
    return {
        "items": items,
        "total": len(items),
        "limit": limit,
    }


@router.post("/sync/items/{item_id}/reset")
async def reset_failed_item(
    item_id: int,
    x_sync_secret: str | None = Header(None, alias="X-Sync-Secret"),
) -> dict[str, Any]:
    _validate_sync_secret(x_sync_secret)

    success = await db.sync_job_item_reset_to_pending(item_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Item {item_id} not found or not in failed/skipped status",
        )

    return {
        "success": True,
        "message": f"Item {item_id} reset to pending",
        "item_id": item_id,
    }


@router.post("/sync/items/{item_id}/skip")
async def skip_failed_item(
    item_id: int,
    reason: str | None = Query(None, description="Reason for skipping"),
    x_sync_secret: str | None = Header(None, alias="X-Sync-Secret"),
) -> dict[str, Any]:
    _validate_sync_secret(x_sync_secret)

    success = await db.sync_job_item_skip(item_id, reason)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Item {item_id} not found or already skipped/completed",
        )

    return {
        "success": True,
        "message": f"Item {item_id} marked as skipped",
        "item_id": item_id,
        "reason": reason or "Manually skipped",
    }


@router.post("/sync/items/{item_id}/delete")
async def delete_sync_item(
    item_id: int,
    x_sync_secret: str | None = Header(None, alias="X-Sync-Secret"),
) -> dict[str, Any]:
    _validate_sync_secret(x_sync_secret)

    success = await db.sync_job_item_delete(item_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")

    return {
        "success": True,
        "message": f"Item {item_id} deleted from sync tracking",
        "item_id": item_id,
    }


@router.post("/sync/jobs/{job_id}/reset-all-failed")
async def reset_all_failed_items(
    job_id: int,
    include_skipped: bool = Query(False, description="Also reset skipped items"),
    x_sync_secret: str | None = Header(None, alias="X-Sync-Secret"),
) -> dict[str, Any]:
    _validate_sync_secret(x_sync_secret)

    job = await db.sync_job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Sync job {job_id} not found")

    reset_count = await db.sync_job_reset_all_failed(job_id, include_skipped=include_skipped)

    return {
        "success": True,
        "message": f"Reset {reset_count} items to pending",
        "job_id": job_id,
        "reset_count": reset_count,
        "include_skipped": include_skipped,
    }

