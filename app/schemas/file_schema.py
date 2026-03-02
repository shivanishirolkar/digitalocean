"""Pydantic schemas for file request/response objects."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class FileResponse(BaseModel):
    """Response schema for a single file.

    Attributes:
        id: Unique file identifier.
        user_id: Owner of the file.
        filename: Original upload filename.
        size_bytes: File size in bytes.
        content_type: MIME type of the file.
        uploaded_at: Timestamp of initial upload.
    """

    id: UUID
    user_id: str
    filename: str
    size_bytes: int
    content_type: str
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class FileListResponse(BaseModel):
    """Paginated list of files.

    Attributes:
        items: List of file response objects.
        total: Total number of files for this user.
        page: Current page number (1-indexed).
        page_size: Number of items per page.
    """

    items: list[FileResponse]
    total: int
    page: int
    page_size: int

    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    """Standard error response body.

    Attributes:
        error: A short error description string.
        details: Optional validation error details.
    """

    error: str
    details: Optional[Any] = None

    model_config = {"from_attributes": True}
