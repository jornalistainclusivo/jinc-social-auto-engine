from jinc_social_engine.domain.entities.version import (
    ApprovalDecision,
    ApprovalDecisionType,
    ContentVersion,
    ContentVersionStatus,
    PublicationAttempt,
    PublicationAttemptStatus,
    ValidationResult,
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


class ContentVersionMapper:
    @staticmethod
    def to_domain(
        version_model: VersionModel,
        validation_models: list[ValidationModel],
        approval_models: list[ApprovalModel],
        attempt_models: list[AttemptModel],
    ) -> ContentVersion:
        validations = [
            ValidationResult(
                id=v.id,
                content_version_id=v.content_version_id,
                is_valid=v.is_valid,
                errors=v.errors,
                created_at=v.created_at,
            )
            for v in validation_models
        ]

        approvals = [
            ApprovalDecision(
                id=a.id,
                content_version_id=a.content_version_id,
                decision_type=ApprovalDecisionType(a.decision_type.value),
                actor_id=a.actor_id,
                edits_made=a.edits_made,
                created_at=a.created_at,
            )
            for a in approval_models
        ]

        attempts = [
            PublicationAttempt(
                id=a.id,
                content_version_id=a.content_version_id,
                worker_id=a.worker_id,
                status=PublicationAttemptStatus(a.status.value),
                external_publication_id=a.external_publication_id,
                failure_reason=a.failure_reason,
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
            for a in attempt_models
        ]

        return ContentVersion(
            id=version_model.id,
            brief_id=version_model.brief_id,
            platform=version_model.platform,
            content=version_model.content,
            status=ContentVersionStatus(version_model.status.value),
            created_at=version_model.created_at,
            updated_at=version_model.updated_at,
            version=version_model.version,
            deleted_at=version_model.deleted_at,
            validation_results=validations,
            approval_decisions=approvals,
            publication_attempts=attempts,
        )
