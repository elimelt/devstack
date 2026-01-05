import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from api import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notes", tags=["notes-search"])

NOTES_SYNC_SECRET = os.getenv("NOTES_SYNC_SECRET", "")


@router.post("/embeddings/generate")
async def generate_embeddings(
    x_sync_secret: str | None = Header(None, alias="X-Sync-Secret"),
) -> dict[str, Any]:
    if not NOTES_SYNC_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Endpoint not configured (NOTES_SYNC_SECRET not set)",
        )

    if x_sync_secret != NOTES_SYNC_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing sync secret")

    try:
        from api.notes_embeddings import generate_embeddings_batch, is_model_available

        if not is_model_available():
            raise HTTPException(
                status_code=503,
                detail="Embedding model not available",
            )

        doc_ids = await db.notes_get_docs_without_embeddings()

        if not doc_ids:
            return {
                "success": True,
                "message": "All documents already have embeddings",
                "processed": 0,
            }

        processed = await generate_embeddings_batch(doc_ids)

        return {
            "success": True,
            "message": f"Generated embeddings for {processed} documents",
            "processed": processed,
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Embedding dependencies not installed",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error generating embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

