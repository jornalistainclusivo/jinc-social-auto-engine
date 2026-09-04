from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from jinc_social_engine.infrastructure.database.adapters.version_repository import (
    SQLAlchemyContentVersionRepository,
)


@pytest.mark.asyncio
async def test_append_only_preserves_history(
    async_session: AsyncSession, create_content_version_in_db
):
    """
    15.4 Append-Only Test
    Ensures that adding a new PublicationAttempt does not delete or overwrite previous.
    """
    version_id = await create_content_version_in_db()
    repo = SQLAlchemyContentVersionRepository(async_session)

    version = await repo.load(version_id)
    assert len(version.publication_attempts) == 0

    now = datetime.now(UTC)

    # Attempt 1
    attempt1 = version.create_attempt(worker_id="worker-1", created_at=now)
    await repo.append_publication_attempt(version_id, attempt1)
    await async_session.flush()

    # Attempt 2
    attempt2 = version.create_attempt(worker_id="worker-2", created_at=now)
    await repo.append_publication_attempt(version_id, attempt2)
    await async_session.flush()

    # Attempt 3
    attempt3 = version.create_attempt(worker_id="worker-3", created_at=now)
    await repo.append_publication_attempt(version_id, attempt3)
    await async_session.flush()

    # Load again to verify
    version_loaded = await repo.load(version_id)
    assert len(version_loaded.publication_attempts) == 3
    assert {a.id for a in version_loaded.publication_attempts} == {
        attempt1.id,
        attempt2.id,
        attempt3.id,
    }
