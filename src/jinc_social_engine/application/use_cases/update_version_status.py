from jinc_social_engine.application.dtos.version import UpdateVersionStatusCommand
from jinc_social_engine.domain.entities.version import ContentVersionStatus
from jinc_social_engine.domain.exceptions import InvariantViolationError
from jinc_social_engine.domain.ports.uow import UnitOfWorkPort


class UpdateVersionStatusUseCase:
    def __init__(self, uow: UnitOfWorkPort):
        self.uow = uow

    async def execute(self, command: UpdateVersionStatusCommand) -> None:
        try:
            new_status = ContentVersionStatus(command.new_status)
        except ValueError:
            raise InvariantViolationError(f"Invalid status: {command.new_status}")

        async with self.uow as uow:
            version = await uow.content_versions.load(command.version_id)
            if not version:
                raise InvariantViolationError(f"Version not found: {command.version_id}")
                
            old_status = version.status

            version.transition_status(new_status)

            await uow.content_versions.transition_status(
                aggregate_id=command.version_id,
                expected_version=command.expected_version,
                new_state=new_status,
            )

            await uow.outbox.append_event(
                aggregate_type="ContentVersion",
                aggregate_id=str(command.version_id),
                event_type=f"VersionStatusChangedTo{new_status.value}",
                payload={"old_status": old_status.value, "new_status": new_status.value},
            )
