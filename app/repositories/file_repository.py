"""Raw database queries for the files table.

No business logic, no validation, no HTTP code — pure data access.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_model import SignedUrlAudit
from app.models.file_model import File


async def create_file(
    db: AsyncSession,
    user_id: str,
    filename: str,
    stored_path: str,
    size_bytes: int,
    content_type: str,
) -> File:
    """Insert a new file row and return the created instance."""
    file = File(
        user_id=user_id,
        filename=filename,
        stored_path=stored_path,
        size_bytes=size_bytes,
        content_type=content_type,
    )
    db.add(file)
    await db.commit()
    await db.refresh(file)
    return file


async def get_file_by_id(db: AsyncSession, file_id: UUID) -> File | None:
    """Return the file matching *file_id*, or ``None``."""
    result = await db.execute(select(File).where(File.id == file_id))
    return result.scalar_one_or_none()


async def get_files_by_user(
    db: AsyncSession,
    user_id: str,
    page: int,
    page_size: int,
) -> tuple[list[File], int]:
    """Return a page of files for *user_id* (1-indexed) plus total count."""
    # Total count
    count_result = await db.execute(
        select(func.count()).select_from(File).where(File.user_id == user_id)
    )
    total = count_result.scalar() or 0

    # Paginated rows
    offset = (page - 1) * page_size
    rows_result = await db.execute(
        select(File)
        .where(File.user_id == user_id)
        .order_by(File.uploaded_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    items = list(rows_result.scalars().all())

    return items, total


async def delete_file(db: AsyncSession, file_id: UUID) -> bool:
    """Delete the file matching *file_id*. Return ``True`` on success, ``False`` if not found."""
    file = await get_file_by_id(db, file_id)
    if file is None:
        return False
    await db.delete(file)
    await db.commit()
    return True


async def get_file_counts(db: AsyncSession) -> dict:
    """Aggregate metrics across the files and signed_url_audit tables.

    Returns a dict with keys: ``total_files``, ``total_size_bytes``,
    ``total_signed_urls``.
    """
    # File metrics
    file_result = await db.execute(
        select(
            func.count(File.id).label("total_files"),
            func.coalesce(func.sum(File.size_bytes), 0).label("total_size_bytes"),
        )
    )
    row = file_result.one()
    total_files = int(row.total_files)
    total_size_bytes = int(row.total_size_bytes)

    # Audit count
    audit_result = await db.execute(
        select(func.count(SignedUrlAudit.id).label("total_signed_urls"))
    )
    total_signed_urls = int(audit_result.scalar() or 0)

    return {
        "total_files": total_files,
        "total_size_bytes": total_size_bytes,
        "total_signed_urls": total_signed_urls,
    }
