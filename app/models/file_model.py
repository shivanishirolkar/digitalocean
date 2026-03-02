"""SQLAlchemy model for the files table."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class File(Base):
    """Represents an uploaded file's metadata.

    Attributes:
        id: Auto-generated UUID primary key.
        user_id: Owner of the file, indexed for fast lookup.
        filename: Original upload filename.
        stored_path: UUID-based path on disk.
        size_bytes: File size in bytes.
        content_type: MIME type of the file.
        uploaded_at: Timestamp of initial upload.
        updated_at: Timestamp of last update.
    """

    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_files_user_id", "user_id"),
    )
