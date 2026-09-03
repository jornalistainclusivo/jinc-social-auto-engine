import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from jinc_social_engine.domain.entities.version import (
    ApprovalDecision,
    ContentVersion,
    ContentVersionStatus,
    PublicationAttempt,
    ValidationResult,
)
from jinc_social_engine.domain.exceptions import ConcurrentModificationError
from jinc_social_engine.domain.ports.repositories import ContentVersionRepository
from jinc_social_engine.infrastructure.database.mappers.version_mapper import (
    ContentVersionMapper,
)
from jinc_social_engine.infrastructure.database.models.approval import (
    ApprovalDecision as ApprovalModel,
)
from jinc_social_engine.infrastructure.database.models.attempt import (
    PublicationAttempt as AttemptModel,
)
from jinc_social_engine.infrastructure.database.models.validation import (
    ValidationResult as ValidationModel,
)
from jinc_social_engine.infrastructure.database.models.version import (
    ContentVersion as VersionModel,
)


class SQLAlchemyContentVersionRepository(ContentVersionRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load(self, version_id: uuid.UUID) -> ContentVersion | None:
        stmt = select(VersionModel).where(
            VersionModel.id == version_id, VersionModel.deleted_at.is_(None)
        )
        result = await self.session.execute(stmt)
        version_model = result.scalar_one_or_none()

        if not version_model:
            return None

        val_stmt = select(ValidationModel).where(
            ValidationModel.content_version_id == version_id
        )
        app_stmt = select(ApprovalModel).where(
            ApprovalModel.content_version_id == version_id
        )
        att_stmt = select(AttemptModel).where(
            AttemptModel.content_version_id == version_id
        )

        val_res = await self.session.execute(val_stmt)
        app_res = await self.session.execute(app_stmt)
        att_res = await self.session.execute(att_stmt)

        return ContentVersionMapper.to_domain(
            version_model,
            list(val_res.scalars().all()),
            list(app_res.scalars().all()),
            list(att_res.scalars().all()),
        )

    async def save_new(self, content_version: ContentVersion) -> None:
        version_model = VersionModel(
            id=content_version.id,
            brief_id=content_version.brief_id,
            platform=content_version.platform,
            content=content_version.content,
            status=content_version.status.value,
            created_at=content_version.created_at,
            updated_at=content_version.updated_at,
            version=content_version.version,
            deleted_at=content_version.deleted_at,
        )
        self.session.add(version_model)

    async def transition_status(
        self,
        aggregate_id: uuid.UUID,
        expected_version: int,
        new_state: ContentVersionStatus,
    ) -> None:
        stmt = (
            update(VersionModel)
            .where(
                VersionModel.id == aggregate_id,
                VersionModel.version == expected_version,
                VersionModel.deleted_at.is_(None),
            )
            .values(
                status=new_state.value,
                version=expected_version + 1,
                updated_at=func.now(),
            )
        )
        result = await self.session.execute(stmt)

        if result.rowcount == 0:
            raise ConcurrentModificationError(
                f"Failed to transition ContentVersion {aggregate_id} to {new_state}. "
                f"Expected version {expected_version} but found otherwise or deleted."
            )

    async def append_publication_attempt(
        self, aggregate_id: uuid.UUID, attempt: PublicationAttempt
    ) -> None:
        model = AttemptModel(
            id=attempt.id,
            content_version_id=aggregate_id,
            worker_id=attempt.worker_id,
            status=attempt.status.value,
            external_publication_id=attempt.external_publication_id,
            failure_reason=attempt.failure_reason,
            created_at=attempt.created_at,
            updated_at=attempt.updated_at,
        )
        self.session.add(model)

    async def append_validation_result(
        self, aggregate_id: uuid.UUID, result: ValidationResult
    ) -> None:
        model = ValidationModel(
            id=result.id,
            content_version_id=aggregate_id,
            is_valid=result.is_valid,
            errors=result.errors,
            created_at=result.created_at,
        )
        self.session.add(model)

    async def append_approval_decision(
        self, aggregate_id: uuid.UUID, decision: ApprovalDecision
    ) -> None:
        model = ApprovalModel(
            id=decision.id,
            content_version_id=aggregate_id,
            decision_type=decision.decision_type.value,
            actor_id=decision.actor_id,
            edits_made=decision.edits_made,
            created_at=decision.created_at,
        )
        self.session.add(model)
