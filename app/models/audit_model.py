"""SQLAlchemy model for the signed_url_audit table."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SignedUrlAudit(Base):
    """Records every signed-URL generation for audit purposes.

    Attributes:
        id: Auto-generated UUID primary key.
        file_id: Foreign key to the file that was signed.
        user_id: User who requested the signed URL.
        ttl_seconds: Requested time-to-live in seconds.
        generated_at: Timestamp when the URL was generated.
        expires_at: Timestamp when the URL expires.
        client_ip: IP address of the requesting client (supports IPv6).
    """

    __tablename__ = "signed_url_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    client_ip: Mapped[str] = mapped_column(String(45), nullable=False)

    __table_args__ = (
        Index("ix_signed_url_audit_file_id", "file_id"),
    )
