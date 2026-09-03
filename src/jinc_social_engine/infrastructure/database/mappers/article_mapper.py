from jinc_social_engine.domain.entities.article import Article, EditorialBrief
from jinc_social_engine.infrastructure.database.models.article import Article as ArticleModel
from jinc_social_engine.infrastructure.database.models.brief import EditorialBrief as BriefModel


class ArticleMapper:
    @staticmethod
    def to_domain(article_model: ArticleModel, brief_models: list[BriefModel]) -> Article:
        briefs = [
            EditorialBrief(
                id=b.id,
                article_id=b.article_id,
                brief_data=b.brief_data,
                created_at=b.created_at,
                updated_at=b.updated_at,
                deleted_at=b.deleted_at,
            )
            for b in brief_models
        ]
        return Article(
            id=article_model.id,
            source_id=article_model.source_id,
            wp_post_id=article_model.wp_post_id,
            url=article_model.url,
            hash=article_model.hash,
            published_at=article_model.published_at,
            created_at=article_model.created_at,
            updated_at=article_model.updated_at,
            deleted_at=article_model.deleted_at,
            editorial_briefs=briefs,
        )
