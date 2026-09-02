import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import UUID_PK, Base, TimestampMixin


class PublicationAttemptStatus(enum.StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class PublicationAttempt(Base, TimestampMixin):
    __tablename__ = "publication_attempts"

    id: Mapped[UUID_PK]
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_versions.id", ondelete="RESTRICT"), nullable=False
    )
    worker_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[PublicationAttemptStatus] = mapped_column(
        Enum(PublicationAttemptStatus, name="publication_attempt_status_enum"),
        nullable=False,
    )
    external_publication_id: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
