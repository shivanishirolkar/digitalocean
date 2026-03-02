"""File management route handlers (upload, list, get, delete, sign, audit).

Thin layer only — calls the service, returns the response.
No business logic or direct queries.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.repositories import audit_repository
from app.schemas.audit_schema import AuditListResponse, SignRequest, SignedUrlResponse
from app.schemas.file_schema import FileListResponse, FileResponse
from app.services import file_service, signing_service

router = APIRouter()
settings = get_settings()


# ---------------------------------------------------------------------------
# POST /files — Upload a file
# ---------------------------------------------------------------------------


@router.post("/files", response_model=FileResponse, status_code=201)
async def upload_file(
    user_id: str = Form(...),
    file: UploadFile = ...,
    db: AsyncSession = Depends(get_db),
):
    """Upload a file via multipart/form-data."""
    try:
        result = await file_service.upload_file(db, user_id, file, settings)
    except ValueError as exc:
        msg = str(exc)
        if msg == "file too large":
            raise HTTPException(status_code=413)
        if msg == "empty file":
            raise HTTPException(status_code=422, detail=msg)
        raise
    return result


# ---------------------------------------------------------------------------
# GET /files — List files for a user
# ---------------------------------------------------------------------------


@router.get("/files", response_model=FileListResponse)
async def list_files(
    user_id: str,
    page: int = 1,
    page_size: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """List files for a given user with pagination."""
    items, total = await file_service.list_files(db, user_id, page, page_size)
    return FileListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


# ---------------------------------------------------------------------------
# GET /files/{file_id} — Get file metadata
# ---------------------------------------------------------------------------


@router.get("/files/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get metadata for a single file."""
    try:
        return await file_service.get_file(db, file_id)
    except ValueError as exc:
        if str(exc) == "file not found":
            raise HTTPException(status_code=404)
        raise


# ---------------------------------------------------------------------------
# DELETE /files/{file_id} — Delete a file
# ---------------------------------------------------------------------------


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: UUID,
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a file from disk and database."""
    try:
        await file_service.delete_file(db, file_id, user_id)
    except ValueError as exc:
        msg = str(exc)
        if msg == "file not found":
            raise HTTPException(status_code=404)
        if msg == "forbidden":
            raise HTTPException(status_code=403)
        raise
    return None


# ---------------------------------------------------------------------------
# POST /files/{file_id}/sign — Generate a signed download URL
# ---------------------------------------------------------------------------


@router.post(
    "/files/{file_id}/sign",
    response_model=SignedUrlResponse,
    status_code=201,
)
async def sign_file(
    file_id: UUID,
    body: SignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Generate a signed download URL for a file."""
    # Verify file exists and user owns it
    try:
        file = await file_service.get_file(db, file_id)
    except ValueError:
        raise HTTPException(status_code=404)

    if file.user_id != body.user_id:
        raise HTTPException(status_code=403)

    # Generate token
    token, expires_at = signing_service.generate_signed_token(
        file_id, body.ttl_seconds, settings.SIGNING_SECRET
    )

    # Record audit event
    client_ip = request.client.host if request.client else "unknown"
    await audit_repository.create_audit_event(
        db=db,
        file_id=file_id,
        user_id=body.user_id,
        ttl_seconds=body.ttl_seconds,
        expires_at=expires_at,
        client_ip=client_ip,
    )

    download_url = f"/download?token={token}"
    return SignedUrlResponse(download_url=download_url, expires_at=expires_at)


# ---------------------------------------------------------------------------
# GET /files/{file_id}/audit — Get audit log for a file
# ---------------------------------------------------------------------------


@router.get(
    "/files/{file_id}/audit",
    response_model=AuditListResponse,
)
async def get_audit_log(
    file_id: UUID,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Get the audit log for a file (owner only)."""
    # Verify file exists and user owns it
    try:
        file = await file_service.get_file(db, file_id)
    except ValueError:
        raise HTTPException(status_code=404)

    if file.user_id != user_id:
        raise HTTPException(status_code=403)

    items, total = await audit_repository.get_audit_events_by_file(
        db, file_id, page, page_size
    )
    return AuditListResponse(
        items=items, total=total, page=page, page_size=page_size
    )
