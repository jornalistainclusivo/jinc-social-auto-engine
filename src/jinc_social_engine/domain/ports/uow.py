from typing import Protocol
from types import TracebackType

from .repositories import ArticleRepository, ContentVersionRepository
from .outbox import OutboxPort


class UnitOfWorkPort(Protocol):
    articles: ArticleRepository
    content_versions: ContentVersionRepository
    outbox: OutboxPort

    async def __aenter__(self) -> "UnitOfWorkPort":
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...
