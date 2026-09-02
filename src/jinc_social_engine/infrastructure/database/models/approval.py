import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .base import UUID_PK, Base, TimestampTZ


class ApprovalDecisionType(str, enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"

    id: Mapped[UUID_PK]
    content_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_versions.id", ondelete="RESTRICT"), nullable=False
    )
    decision_type: Mapped[ApprovalDecisionType] = mapped_column(
        Enum(ApprovalDecisionType, name="approval_decision_type_enum"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    edits_made: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[TimestampTZ] = mapped_column(server_default=func.now())
