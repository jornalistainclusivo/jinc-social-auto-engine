import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .base import UUID_PK, Base, TimestampTZ


class ActorType(enum.StrEnum):
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"
    WORKER = "WORKER"


class ContentVersionTransition(Base):
    """
    Append-only audit table for ContentVersion state transitions.
    """

    __tablename__ = "content_version_transitions"

    id: Mapped[UUID_PK]
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_versions.id", ondelete="RESTRICT"), nullable=False
    )
    from_state: Mapped[str] = mapped_column(String, nullable=False)
    to_state: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="actor_type_enum"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    timestamp: Mapped[TimestampTZ] = mapped_column(server_default=func.now())
