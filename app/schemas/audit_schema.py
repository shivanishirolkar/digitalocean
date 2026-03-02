"""Pydantic schemas for audit and signing request/response objects."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator


class SignRequest(BaseModel):
    """Request schema for generating a signed download URL.

    Attributes:
        user_id: Must match the file owner.
        ttl_seconds: Time-to-live in seconds (60–86400). Defaults to 3600.
    """

    user_id: str
    ttl_seconds: int = 3600

    @field_validator("ttl_seconds")
    @classmethod
    def validate_ttl(cls, v: int) -> int:
        """Ensure ttl_seconds is between 60 and 86400."""
        if not 60 <= v <= 86400:
            raise ValueError("ttl_seconds must be between 60 and 86400")
        return v


class SignedUrlResponse(BaseModel):
    """Response schema for a generated signed URL.

    Attributes:
        download_url: The signed download URL path with token.
        expires_at: Timestamp when the signed URL expires.
    """

    download_url: str
    expires_at: datetime

    model_config = {"from_attributes": True}


class AuditEventResponse(BaseModel):
    """Response schema for a single audit event.

    Attributes:
        id: Unique audit event identifier.
        file_id: The file that was signed.
        user_id: User who requested the signed URL.
        generated_at: Timestamp when the URL was generated.
        expires_at: Timestamp when the URL expires.
        client_ip: IP address of the requesting client.
    """

    id: UUID
    file_id: UUID
    user_id: str
    generated_at: datetime
    expires_at: datetime
    client_ip: str

    model_config = {"from_attributes": True}


class AuditListResponse(BaseModel):
    """Paginated list of audit events.

    Attributes:
        items: List of audit event response objects.
        total: Total number of audit events for this file.
        page: Current page number (1-indexed).
        page_size: Number of items per page.
    """

    items: list[AuditEventResponse]
    total: int
    page: int
    page_size: int

    model_config = {"from_attributes": True}
