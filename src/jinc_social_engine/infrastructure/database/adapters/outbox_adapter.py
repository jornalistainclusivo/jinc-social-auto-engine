import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jinc_social_engine.domain.ports.outbox import OutboxPort
from jinc_social_engine.infrastructure.database.models.outbox import (
    OutboxEvent,
    OutboxStatus,
)


class SQLAlchemyOutboxAdapter(OutboxPort):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def append_event(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        event = OutboxEvent(
            id=uuid.uuid4(),
            aggregate_type=aggregate_type,
            aggregate_id=uuid.UUID(aggregate_id),
            event_type=event_type,
            payload=payload,
            status=OutboxStatus.PENDING,
        )
        self.session.add(event)
