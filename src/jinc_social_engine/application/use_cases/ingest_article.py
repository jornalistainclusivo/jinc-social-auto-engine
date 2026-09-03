import uuid
from datetime import datetime, timezone

from jinc_social_engine.application.dtos.article import IngestArticleCommand
from jinc_social_engine.domain.entities.article import Article
from jinc_social_engine.domain.ports.uow import UnitOfWorkPort


class IngestArticleUseCase:
    def __init__(self, uow: UnitOfWorkPort):
        self.uow = uow

    async def execute(self, command: IngestArticleCommand) -> uuid.UUID:
        async with self.uow as uow:
            now = datetime.now(timezone.utc)
            article_id = uuid.uuid4()
            article = Article(
                id=article_id,
                source_id=command.source_id,
                wp_post_id=command.wp_post_id,
                url=command.url,
                hash=command.hash,
                published_at=command.published_at,
                created_at=now,
                updated_at=now,
            )
            article.add_brief(brief_data=command.brief_data, created_at=now)

            await uow.articles.save_new(article)

            await uow.outbox.append_event(
                aggregate_type="Article",
                aggregate_id=str(article_id),
                event_type="ArticleIngested",
                payload={"wp_post_id": command.wp_post_id},
            )

        return article_id
