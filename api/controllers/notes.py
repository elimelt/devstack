from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api import db

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("")
async def list_notes(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip"),
) -> dict[str, Any]:
    documents = await db.notes_fetch_documents(limit=limit, offset=offset)
    total = await db.notes_count_documents()

    return {
        "documents": documents,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(documents) < total,
    }


@router.get("/tags")
async def list_tags() -> dict[str, Any]:
    tags = await db.notes_get_all_tags()
    return {"tags": tags}


@router.get("/categories")
async def list_categories() -> dict[str, Any]:
    categories = await db.notes_get_all_categories()
    return {"categories": categories}


@router.get("/category/{category}")
async def get_notes_by_category(
    category: str,
    limit: int = Query(50, ge=1, le=200, description="Maximum number of documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip"),
) -> dict[str, Any]:
    cat = await db.notes_get_category_by_name(category)
    if not cat:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found")

    documents = await db.notes_fetch_documents(category_id=cat["id"], limit=limit, offset=offset)
    total = await db.notes_count_documents(category_id=cat["id"])

    return {
        "category": category,
        "documents": documents,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(documents) < total,
    }


@router.get("/tags/{tag}")
async def get_notes_by_tag(
    tag: str,
    limit: int = Query(50, ge=1, le=200, description="Maximum number of documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip"),
) -> dict[str, Any]:
    tag_obj = await db.notes_get_tag_by_name(tag)
    if not tag_obj:
        raise HTTPException(status_code=404, detail=f"Tag '{tag}' not found")

    documents = await db.notes_fetch_documents(tag_id=tag_obj["id"], limit=limit, offset=offset)
    total = await db.notes_count_documents(tag_id=tag_obj["id"])

    return {
        "tag": tag,
        "documents": documents,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(documents) < total,
    }


@router.get("/{doc_id:int}")
async def get_note(doc_id: int) -> dict[str, Any]:
    document = await db.notes_get_document_by_id(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document with id {doc_id} not found")

    return {"document": document}


@router.get("/sync/jobs")
async def list_sync_jobs(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of jobs to return"),
    status: str | None = Query(None, description="Filter by job status"),
) -> dict[str, Any]:
    jobs = await db.sync_job_list(limit=limit, status=status)
    return {"jobs": jobs}


@router.get("/sync/jobs/{job_id}")
async def get_sync_job(job_id: int) -> dict[str, Any]:
    job = await db.sync_job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Sync job {job_id} not found")

    failed_items = await db.sync_job_get_failed_items(job_id)

    return {
        "job": job,
        "failed_items": failed_items,
    }
