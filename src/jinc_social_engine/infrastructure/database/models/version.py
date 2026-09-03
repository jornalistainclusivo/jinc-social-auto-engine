import enum
import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import UUID_PK, Base, SoftDeleteMixin, TimestampMixin


class ContentVersionStatus(enum.StrEnum):
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SCHEDULED = "SCHEDULED"
    PUBLISHING = "PUBLISHING"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    PUBLISHED = "PUBLISHED"


class ContentVersion(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "content_versions"

    id: Mapped[UUID_PK]
    brief_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("editorial_briefs.id", ondelete="RESTRICT"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[ContentVersionStatus] = mapped_column(
        Enum(ContentVersionStatus, name="content_version_status_enum"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(nullable=False, server_default="1", default=1)

    __table_args__ = (
        CheckConstraint(
            "status IN ('GENERATED', 'VALIDATED', 'PENDING_REVIEW', "
            "'APPROVED', 'REJECTED', 'SCHEDULED', 'PUBLISHING', "
            "'PUBLISH_FAILED', 'PUBLISHED')",
            name="ck_content_versions_status",
        ),
        Index(
            "idx_content_versions_publishing",
            "updated_at",
            postgresql_where=text("status = 'PUBLISHING'"),
        ),
    )
