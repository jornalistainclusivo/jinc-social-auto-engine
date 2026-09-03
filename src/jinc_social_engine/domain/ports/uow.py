from types import TracebackType
from typing import Protocol

from .outbox import OutboxPort
from .repositories import ArticleRepository, ContentVersionRepository


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
