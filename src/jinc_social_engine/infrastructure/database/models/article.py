from sqlalchemy import BigInteger, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import UUID_PK, Base, SoftDeleteMixin, TimestampMixin, TimestampTZ


class Article(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "articles"

    id: Mapped[UUID_PK]
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    wp_post_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    hash: Mapped[str] = mapped_column(String, nullable=False)
    published_at: Mapped[TimestampTZ] = mapped_column(nullable=False)

    __table_args__ = (
        Index(
            "uq_articles_source_wp",
            "source_id",
            "wp_post_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
