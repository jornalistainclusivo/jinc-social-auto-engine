from typing import Any, Protocol


class OutboxPort(Protocol):
    async def append_event(
        self, aggregate_type: str, aggregate_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        """Appends an event to the outbox."""
        ...
