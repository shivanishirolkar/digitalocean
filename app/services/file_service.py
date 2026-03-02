"""Service for file upload, retrieval, listing, and deletion logic.

Business logic only — no direct queries, no HTTP code.
All database access goes through the repository layer.
"""

import os
import uuid
from pathlib import Path
from uuid import UUID

import aiofiles
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.file_model import File
from app.repositories import file_repository


async def upload_file(
    db: AsyncSession,
    user_id: str,
    file: UploadFile,
    settings: Settings,
) -> File:
    """Validate, persist to disk, and store metadata for an uploaded file.

    Args:
        db: Async database session.
        user_id: Owner identifier.
        file: The uploaded file object.
        settings: Application settings (MAX_FILE_SIZE, UPLOAD_DIR).

    Returns:
        The created File model instance.

    Raises:
        ValueError: If file is empty or exceeds MAX_FILE_SIZE.
    """
    # Read file content and validate size
    content = await file.read()

    if len(content) == 0:
        raise ValueError("empty file")

    if len(content) > settings.MAX_FILE_SIZE:
        raise ValueError("file too large")

    # Generate UUID-based stored filename, preserving original extension
    original_filename = file.filename or "upload"
    ext = Path(original_filename).suffix  # e.g. ".pdf"
    stored_name = f"{uuid.uuid4()}{ext}"
    stored_path = os.path.join(settings.UPLOAD_DIR, stored_name)

    # Write file to disk
    async with aiofiles.open(stored_path, "wb") as f:
        await f.write(content)

    # Insert metadata into the database
    try:
        db_file = await file_repository.create_file(
            db=db,
            user_id=user_id,
            filename=original_filename,
            stored_path=stored_path,
            size_bytes=len(content),
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception:
        # Clean up the file from disk if DB insert fails
        try:
            os.remove(stored_path)
        except FileNotFoundError:
            pass
        raise

    return db_file


async def get_file(db: AsyncSession, file_id: UUID) -> File:
    """Retrieve a single file by ID.

    Raises:
        ValueError: If file not found.
    """
    file = await file_repository.get_file_by_id(db, file_id)
    if file is None:
        raise ValueError("file not found")
    return file


async def list_files(
    db: AsyncSession,
    user_id: str,
    page: int,
    page_size: int,
) -> tuple[list[File], int]:
    """Return a paginated list of files for a user."""
    return await file_repository.get_files_by_user(db, user_id, page, page_size)


async def delete_file(
    db: AsyncSession,
    file_id: UUID,
    user_id: str,
) -> None:
    """Delete a file from disk and database.

    Raises:
        ValueError: If file not found or user does not own the file.
    """
    file = await file_repository.get_file_by_id(db, file_id)
    if file is None:
        raise ValueError("file not found")
    if file.user_id != user_id:
        raise ValueError("forbidden")

    # Remove file from disk (ignore if already gone)
    try:
        os.remove(file.stored_path)
    except FileNotFoundError:
        pass

    # Remove database record
    await file_repository.delete_file(db, file_id)
