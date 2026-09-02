import uuid
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import UUID_PK, Base, SoftDeleteMixin, TimestampMixin


class EditorialBrief(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "editorial_briefs"

    id: Mapped[UUID_PK]
    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("articles.id", ondelete="RESTRICT"), nullable=False
    )
    brief_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
