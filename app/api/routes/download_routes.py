"""Public download route handler for signed URL file retrieval.

No API key required. Validates the signed token and streams the file.
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.services import file_service, signing_service

router = APIRouter()
settings = get_settings()

CHUNK_SIZE = 64 * 1024  # 64 KB


@router.get("/download")
async def download_file(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Download a file using a signed token.

    Validates the HMAC signature and expiry, then streams the file
    with the correct Content-Type and Content-Disposition headers.
    """
    # Verify the signed token
    try:
        file_id = signing_service.verify_signed_token(token, settings.SIGNING_SECRET)
    except ValueError as exc:
        msg = str(exc)
        if msg == "invalid signature":
            raise HTTPException(status_code=403)
        if msg == "link expired":
            raise HTTPException(status_code=410)
        raise

    # Look up the file in the database
    try:
        file = await file_service.get_file(db, file_id)
    except ValueError:
        raise HTTPException(status_code=404)

    # Verify the file exists on disk
    if not os.path.isfile(file.stored_path):
        raise HTTPException(status_code=404)

    # Stream the file
    def _iter_file():
        with open(file.stored_path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                yield chunk

    return StreamingResponse(
        _iter_file(),
        media_type=file.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file.filename}"',
        },
    )
