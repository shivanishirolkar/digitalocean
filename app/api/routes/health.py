"""Health and metrics endpoints."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    """Liveness check with database connectivity test.

    Returns:
        dict: Status and database connection state.
    """
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as exc:
        logger.exception("health check database failure")
        return {"status": "unhealthy", "database": "unreachable"}


@router.get("/metrics")
async def metrics() -> dict:
    """Return file-store metrics (placeholder).

    Returns:
        dict: Hardcoded zeros until wired to the database.
    """
    # TODO: replace with get_file_counts(db)
    return {"total_files": 0, "total_size_bytes": 0, "total_signed_urls": 0}
