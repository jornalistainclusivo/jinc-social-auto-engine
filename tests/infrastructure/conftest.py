import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from jinc_social_engine.domain.entities.version import ContentVersionStatus


@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:16-alpine") as postgres:
        url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
        yield url


@pytest.fixture(scope="session")
def apply_migrations(postgres_url):
    # Set DATABASE_URL for env.py
    os.environ["DATABASE_URL"] = postgres_url

    # Run Alembic migrations
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

    yield

    # Optionally, we could downgrade or just let the container die
    pass


@pytest_asyncio.fixture(scope="session")
async def async_engine(postgres_url, apply_migrations):
    engine = create_async_engine(postgres_url, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine):
    async_session = async_sessionmaker(
        async_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with async_session() as session:
        # Start a transaction that we will rollback after the test
        async with session.begin():
            yield session
            await session.rollback()


@pytest.fixture
def async_session(db_session):
    return db_session


@pytest.fixture
def async_session_factory(async_engine):
    return async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def create_content_version_in_db(async_session_factory):
    async def _create(
        status: ContentVersionStatus = ContentVersionStatus.GENERATED,
        version: int = 1,
    ) -> uuid.UUID:
        from jinc_social_engine.infrastructure.database.models.article import Article
        from jinc_social_engine.infrastructure.database.models.brief import (
            EditorialBrief,
        )
        from jinc_social_engine.infrastructure.database.models.version import (
            ContentVersion,
        )

        article_id = uuid.uuid4()
        brief_id = uuid.uuid4()
        version_id = uuid.uuid4()

        now = datetime.now(UTC)

        article = Article(
            id=article_id,
            source_id=f"test-source-{uuid.uuid4()}",
            wp_post_id=int(now.timestamp()),
            url="http://test.com",
            hash=str(uuid.uuid4()),
            published_at=now,
            created_at=now,
            updated_at=now,
        )

        brief = EditorialBrief(
            id=brief_id,
            article_id=article_id,
            brief_data={"test": "data"},
            created_at=now,
            updated_at=now,
        )

        model = ContentVersion(
            id=version_id,
            brief_id=brief_id,
            platform="twitter",
            content="test content",
            version=version,
            status=status,
            created_at=now,
            updated_at=now,
        )
        async with async_session_factory() as session:
            session.add(article)
            session.add(brief)
            session.add(model)
            await session.commit()
        return version_id

    return _create
