import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from jinc_social_engine.domain.exceptions import StateTransitionRejected


class ContentVersionStatus(enum.StrEnum):
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SCHEDULED = "SCHEDULED"
    PUBLISHING = "PUBLISHING"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    PUBLISHED = "PUBLISHED"


class ApprovalDecisionType(enum.StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PublicationAttemptStatus(enum.StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass
class ValidationResult:
    id: uuid.UUID
    content_version_id: uuid.UUID
    is_valid: bool
    errors: dict[str, Any]
    created_at: datetime


@dataclass
class ApprovalDecision:
    id: uuid.UUID
    content_version_id: uuid.UUID
    decision_type: ApprovalDecisionType
    actor_id: str
    edits_made: dict[str, Any] | None
    created_at: datetime


@dataclass
class PublicationAttempt:
    id: uuid.UUID
    content_version_id: uuid.UUID
    worker_id: str
    status: PublicationAttemptStatus
    external_publication_id: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class ContentVersion:
    id: uuid.UUID
    brief_id: uuid.UUID
    platform: str
    content: str
    status: ContentVersionStatus
    created_at: datetime
    updated_at: datetime
    version: int = 1
    deleted_at: datetime | None = None

    validation_results: list[ValidationResult] = field(default_factory=list)
    approval_decisions: list[ApprovalDecision] = field(default_factory=list)
    publication_attempts: list[PublicationAttempt] = field(default_factory=list)

    def transition_status(self, new_status: ContentVersionStatus):
        allowed_transitions = {
            ContentVersionStatus.GENERATED: [ContentVersionStatus.VALIDATED],
            ContentVersionStatus.VALIDATED: [ContentVersionStatus.PENDING_REVIEW],
            ContentVersionStatus.PENDING_REVIEW: [ContentVersionStatus.APPROVED, ContentVersionStatus.REJECTED],
            ContentVersionStatus.APPROVED: [ContentVersionStatus.SCHEDULED],
            ContentVersionStatus.SCHEDULED: [ContentVersionStatus.PUBLISHING],
            ContentVersionStatus.PUBLISHING: [ContentVersionStatus.PUBLISHED, ContentVersionStatus.PUBLISH_FAILED],
            ContentVersionStatus.PUBLISH_FAILED: [ContentVersionStatus.PUBLISHING],
        }

        if new_status not in allowed_transitions.get(self.status, []):
            raise StateTransitionRejected(f"Cannot transition from {self.status} to {new_status}")

        self.status = new_status
        self.version += 1

    def create_attempt(self, worker_id: str, created_at: datetime) -> PublicationAttempt:
        attempt = PublicationAttempt(
            id=uuid.uuid4(),
            content_version_id=self.id,
            worker_id=worker_id,
            status=PublicationAttemptStatus.PENDING,
            external_publication_id=None,
            failure_reason=None,
            created_at=created_at,
            updated_at=created_at,
        )
        self.publication_attempts.append(attempt)
        return attempt

    def add_validation_result(self, is_valid: bool, errors: dict[str, Any], created_at: datetime) -> ValidationResult:
        result = ValidationResult(
            id=uuid.uuid4(),
            content_version_id=self.id,
            is_valid=is_valid,
            errors=errors,
            created_at=created_at,
        )
        self.validation_results.append(result)
        return result

    def add_approval_decision(self, decision_type: ApprovalDecisionType, actor_id: str, edits_made: dict[str, Any] | None, created_at: datetime) -> ApprovalDecision:
        decision = ApprovalDecision(
            id=uuid.uuid4(),
            content_version_id=self.id,
            decision_type=decision_type,
            actor_id=actor_id,
            edits_made=edits_made,
            created_at=created_at,
        )
        self.approval_decisions.append(decision)
        return decision
