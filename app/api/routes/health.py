"""Health and metrics endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Liveness check endpoint.

    Returns:
        dict: ``{"status": "ok"}`` when the service is running.
    """
    return {"status": "ok"}


@router.get("/metrics")
async def metrics() -> dict:
    """Return file-store metrics (placeholder).

    Returns:
        dict: Hardcoded zeros until wired to the database.
    """
    # TODO: replace with get_file_counts(db)
    return {"total_files": 0, "total_size_bytes": 0, "total_signed_urls": 0}
