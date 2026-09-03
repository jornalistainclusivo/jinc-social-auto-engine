from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from jinc_social_engine.domain.ports.uow import UnitOfWorkPort
from jinc_social_engine.infrastructure.database.adapters.article_repository import (
    SQLAlchemyArticleRepository,
)
from jinc_social_engine.infrastructure.database.adapters.outbox_adapter import (
    SQLAlchemyOutboxAdapter,
)
from jinc_social_engine.infrastructure.database.adapters.version_repository import (
    SQLAlchemyContentVersionRepository,
)


class SQLAlchemyUnitOfWork(UnitOfWorkPort):
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> "SQLAlchemyUnitOfWork":
        self.session = self.session_factory()
        self.articles = SQLAlchemyArticleRepository(self.session)
        self.content_versions = SQLAlchemyContentVersionRepository(self.session)
        self.outbox = SQLAlchemyOutboxAdapter(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
            
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()
            
        await self.session.close()

    async def commit(self) -> None:
        if self.session:
            await self.session.commit()

    async def rollback(self) -> None:
        if self.session:
            await self.session.rollback()
