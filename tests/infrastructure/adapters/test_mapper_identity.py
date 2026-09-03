from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from jinc_social_engine.domain.entities.version import (
    ApprovalDecisionType,
    ContentVersionStatus,
)
from jinc_social_engine.infrastructure.database.adapters.version_repository import (
    SQLAlchemyContentVersionRepository,
)


@pytest.mark.asyncio
async def test_mapper_identity_no_destructive_updates(
    async_session: AsyncSession, create_content_version_in_db
):
    """
    15.6 Mapper / Identity Test
    Test ORM -> Domain -> Mutation -> targeted persistence without deleting relations.
    """
    version_id = await create_content_version_in_db(
        status=ContentVersionStatus.GENERATED, version=1
    )
    repo = SQLAlchemyContentVersionRepository(async_session)

    # 1. Load from DB
    version = await repo.load(version_id)

    # 2. Add an approval decision
    now = datetime.now(UTC)
    decision = version.add_approval_decision(
        decision_type=ApprovalDecisionType.APPROVED,
        actor_id="reviewer-1",
        edits_made=None,
        created_at=now,
    )
    await repo.append_approval_decision(version_id, decision)

    # 3. Transition status
    version.transition_status(ContentVersionStatus.APPROVED)
    await repo.transition_status(
        aggregate_id=version_id,
        expected_version=version.version
        - 1,  # transition_status increments the domain version
        new_state=ContentVersionStatus.APPROVED,
    )

    await async_session.commit()

    # 4. Verify no loss of history or missing data
    version_reloaded = await repo.load(version_id)
    assert version_reloaded.status == ContentVersionStatus.APPROVED
    assert version_reloaded.version == 2
    assert len(version_reloaded.approval_decisions) == 1
    assert version_reloaded.approval_decisions[0].actor_id == "reviewer-1"
