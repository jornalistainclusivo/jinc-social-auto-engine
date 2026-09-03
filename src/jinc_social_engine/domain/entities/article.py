import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class EditorialBrief:
    id: uuid.UUID
    article_id: uuid.UUID
    brief_data: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


@dataclass
class Article:
    id: uuid.UUID
    source_id: str
    wp_post_id: int
    url: str
    hash: str
    published_at: datetime
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    editorial_briefs: list[EditorialBrief] = field(default_factory=list)

    def add_brief(
        self, brief_data: dict[str, Any], created_at: datetime
    ) -> EditorialBrief:
        brief = EditorialBrief(
            id=uuid.uuid4(),
            article_id=self.id,
            brief_data=brief_data,
            created_at=created_at,
            updated_at=created_at,
        )
        self.editorial_briefs.append(brief)
        return brief
