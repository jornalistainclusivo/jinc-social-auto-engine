from datetime import UTC

import pytest
from sqlalchemy import select

from jinc_social_engine.infrastructure.database.models import Article


@pytest.mark.asyncio
async def test_article_insertion(db_session):
    """
    Test that we can insert an Article and it generates a UUID and timestamps correctly.
    """
    article = Article(
        source_id="wp_123",
        wp_post_id=123,
        url="https://example.com/article-123",
        hash="abcdef123456",
        # published_at must be provided as it's not server_default
    )

    # We need a timezone aware datetime for TIMESTAMPTZ
    from datetime import datetime

    article.published_at = datetime.now(UTC)

    db_session.add(article)
    await db_session.flush()

    assert article.id is not None
    assert article.created_at is not None
    assert article.updated_at is not None
    assert article.deleted_at is None

    # Query it back
    result = await db_session.execute(select(Article).where(Article.id == article.id))
    db_article = result.scalar_one()

    assert db_article.source_id == "wp_123"
    assert db_article.wp_post_id == 123
