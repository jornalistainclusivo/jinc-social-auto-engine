import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic.config import Config
from alembic import command


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
