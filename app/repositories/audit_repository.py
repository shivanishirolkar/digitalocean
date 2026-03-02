"""Raw database queries for the signed_url_audit table.

No business logic, no validation, no HTTP code — pure data access.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_model import SignedUrlAudit


async def create_audit_event(
    db: AsyncSession,
    file_id: UUID,
    user_id: str,
    ttl_seconds: int,
    expires_at: datetime,
    client_ip: str,
) -> SignedUrlAudit:
    """Insert a new audit row and return the created instance."""
    event = SignedUrlAudit(
        file_id=file_id,
        user_id=user_id,
        ttl_seconds=ttl_seconds,
        expires_at=expires_at,
        client_ip=client_ip,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def get_audit_events_by_file(
    db: AsyncSession,
    file_id: UUID,
    page: int,
    page_size: int,
) -> tuple[list[SignedUrlAudit], int]:
    """Return a page of audit events for *file_id* (1-indexed) plus total count."""
    # Total count
    count_result = await db.execute(
        select(func.count())
        .select_from(SignedUrlAudit)
        .where(SignedUrlAudit.file_id == file_id)
    )
    total = count_result.scalar() or 0

    # Paginated rows
    offset = (page - 1) * page_size
    rows_result = await db.execute(
        select(SignedUrlAudit)
        .where(SignedUrlAudit.file_id == file_id)
        .order_by(SignedUrlAudit.generated_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    items = list(rows_result.scalars().all())

    return items, total
