
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from jinc_social_engine.domain.entities.version import ContentVersionStatus
from jinc_social_engine.domain.exceptions import ConcurrentModificationError
from jinc_social_engine.infrastructure.database.adapters.version_repository import (
    SQLAlchemyContentVersionRepository,
)


@pytest.mark.asyncio
async def test_cas_concurrency(async_session: AsyncSession, create_content_version_in_db):
    """
    15.2 CAS Concurrency Test
    Ensures that ConcurrentModificationError is raised when two transactions try to update
    the same version simultaneously bypassing the CAS check.
    """
    version_id = await create_content_version_in_db(status=ContentVersionStatus.GENERATED, version=1)

    repo_t1 = SQLAlchemyContentVersionRepository(async_session)
    repo_t2 = SQLAlchemyContentVersionRepository(async_session)

    # T1 loads
    version_t1 = await repo_t1.load(version_id)
    assert version_t1 is not None
    assert version_t1.version == 1

    # T2 loads
    version_t2 = await repo_t2.load(version_id)
    assert version_t2 is not None
    assert version_t2.version == 1

    # T1 transitions
    await repo_t1.transition_status(
        aggregate_id=version_id,
        expected_version=version_t1.version,
        new_state=ContentVersionStatus.VALIDATED
    )
    await async_session.commit() # Flush T1 to DB

    # T2 attempts to transition with outdated expected_version
    with pytest.raises(ConcurrentModificationError):
        await repo_t2.transition_status(
            aggregate_id=version_id,
            expected_version=version_t2.version,
            new_state=ContentVersionStatus.VALIDATED
        )
