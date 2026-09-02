import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .base import UUID_PK, Base, TimestampTZ


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[UUID_PK]
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_versions.id", ondelete="RESTRICT"), nullable=False
    )
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    errors: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[TimestampTZ] = mapped_column(server_default=func.now())
