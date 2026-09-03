import uuid
from typing import Any, Protocol

from jinc_social_engine.domain.entities.article import Article
from jinc_social_engine.domain.entities.version import (
    ApprovalDecision,
    ApprovalDecisionType,
    ContentVersion,
    ContentVersionStatus,
    PublicationAttempt,
    ValidationResult,
)


class ArticleRepository(Protocol):
    async def load(self, article_id: uuid.UUID) -> Article | None:
        """Loads an article with its briefs."""
        ...

    async def save_new(self, article: Article) -> None:
        """Saves a new article."""
        ...


class ContentVersionRepository(Protocol):
    async def load(self, version_id: uuid.UUID) -> ContentVersion | None:
        """Loads a content version with all its nested entities."""
        ...

    async def save_new(self, content_version: ContentVersion) -> None:
        """Saves a new content version."""
        ...

    async def transition_status(
        self,
        aggregate_id: uuid.UUID,
        expected_version: int,
        new_state: ContentVersionStatus,
    ) -> None:
        """
        Executes a CAS (Compare-And-Swap) state transition.
        Must raise ConcurrentModificationError if the record doesn't match expected_version.
        """
        ...

    async def append_publication_attempt(
        self, aggregate_id: uuid.UUID, attempt: PublicationAttempt
    ) -> None:
        """Appends a new publication attempt."""
        ...

    async def append_validation_result(
        self, aggregate_id: uuid.UUID, result: ValidationResult
    ) -> None:
        """Appends a validation result."""
        ...

    async def append_approval_decision(
        self, aggregate_id: uuid.UUID, decision: ApprovalDecision
    ) -> None:
        """Appends an approval decision."""
        ...
