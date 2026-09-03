import pytest

from jinc_social_engine.application.dtos.version import UpdateVersionStatusCommand
from jinc_social_engine.application.use_cases.update_version_status import (
    UpdateVersionStatusUseCase,
)
from jinc_social_engine.domain.entities.version import ContentVersionStatus
from jinc_social_engine.infrastructure.database.uow import SQLAlchemyUnitOfWork


@pytest.mark.asyncio
async def test_uow_atomicity_rollback_on_error(
    async_session_factory, create_content_version_in_db
):
    """
    15.3 Atomicity Test
    Ensures that if an error occurs during the UoW, the transaction is rolled back,
    including domain state changes and outbox events.
    """
    version_id = await create_content_version_in_db(
        status=ContentVersionStatus.GENERATED, version=1
    )

    uow = SQLAlchemyUnitOfWork(async_session_factory)

    class ForcedException(Exception):
        pass

    # We mock the outbox to raise an exception after the state transition

    try:
        async with uow as ctx:

            async def failing_append(*args, **kwargs):
                raise ForcedException("Forced failure")

            ctx.outbox.append_event = failing_append

            use_case = UpdateVersionStatusUseCase(uow=ctx)
            command = UpdateVersionStatusCommand(
                version_id=version_id, expected_version=1, new_status="VALIDATED"
            )

            await use_case.execute(command)

    except ForcedException:
        pass

    # Verify rollback in a new UoW
    async with SQLAlchemyUnitOfWork(async_session_factory) as verify_uow:
        version = await verify_uow.content_versions.load(version_id)
        # Should not have transitioned to VALIDATED because of rollback
        assert version.status == ContentVersionStatus.GENERATED
        assert version.version == 1
