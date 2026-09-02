import enum
import uuid
from typing import Any

from sqlalchemy import Enum, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .base import UUID_PK, Base, TimestampTZ


class OutboxStatus(enum.StrEnum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[UUID_PK]
    aggregate_type: Mapped[str] = mapped_column(String, nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, name="outbox_status_enum"), nullable=False, index=True
    )
    created_at: Mapped[TimestampTZ] = mapped_column(server_default=func.now())
    processed_at: Mapped[TimestampTZ | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index(
            "idx_outbox_events_status",
            "status",
            postgresql_where=text("status = 'PENDING'"),
        ),
    )
