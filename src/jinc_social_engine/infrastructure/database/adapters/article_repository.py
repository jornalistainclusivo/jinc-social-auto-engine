import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jinc_social_engine.domain.entities.article import Article
from jinc_social_engine.domain.ports.repositories import ArticleRepository
from jinc_social_engine.infrastructure.database.mappers.article_mapper import ArticleMapper
from jinc_social_engine.infrastructure.database.models.article import Article as ArticleModel
from jinc_social_engine.infrastructure.database.models.brief import (
    EditorialBrief as BriefModel,
)


class SQLAlchemyArticleRepository(ArticleRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load(self, article_id: uuid.UUID) -> Article | None:
        stmt = select(ArticleModel).where(
            ArticleModel.id == article_id, ArticleModel.deleted_at.is_(None)
        )
        result = await self.session.execute(stmt)
        article_model = result.scalar_one_or_none()
        
        if not article_model:
            return None

        brief_stmt = select(BriefModel).where(
            BriefModel.article_id == article_id, BriefModel.deleted_at.is_(None)
        )
        brief_result = await self.session.execute(brief_stmt)
        brief_models = list(brief_result.scalars().all())

        return ArticleMapper.to_domain(article_model, brief_models)

    async def save_new(self, article: Article) -> None:
        article_model = ArticleModel(
            id=article.id,
            source_id=article.source_id,
            wp_post_id=article.wp_post_id,
            url=article.url,
            hash=article.hash,
            published_at=article.published_at,
            created_at=article.created_at,
            updated_at=article.updated_at,
            deleted_at=article.deleted_at,
        )
        self.session.add(article_model)

        for b in article.editorial_briefs:
            brief_model = BriefModel(
                id=b.id,
                article_id=b.article_id,
                brief_data=b.brief_data,
                created_at=b.created_at,
                updated_at=b.updated_at,
                deleted_at=b.deleted_at,
            )
            self.session.add(brief_model)
