import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class IngestArticleCommand(BaseModel):
    source_id: str
    wp_post_id: int
    url: str
    hash: str
    published_at: datetime
    brief_data: dict[str, Any]
