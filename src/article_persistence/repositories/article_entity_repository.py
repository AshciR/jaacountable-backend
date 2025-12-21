from pathlib import Path
from datetime import datetime, timezone
import aiosql
import asyncpg

from src.article_persistence.models.domain import ArticleEntity


class ArticleEntityRepository:
    """Repository for article-entity junction table operations using aiosql."""

    def __init__(self):
        """Initialize the repository and load SQL queries."""
        queries_path = Path(__file__).parent.parent / "queries"
        self.queries = aiosql.from_path(str(queries_path), "asyncpg")

    async def link_article_to_entity(
        self,
        conn: asyncpg.Connection,
        article_entity: ArticleEntity,
    ) -> ArticleEntity:
        """
        Link article to entity with classifier type.

        Args:
            conn: Database connection to use for the query
            article_entity: ArticleEntity to insert (id will be ignored)

        Returns:
            ArticleEntity: Created association with database-generated id

        Raises:
            asyncpg.UniqueViolationError: If (article_id, entity_id) pair already exists
            asyncpg.ForeignKeyViolationError: If article_id or entity_id doesn't exist
        """
        result = await self.queries.insert_article_entity(
            conn,
            article_id=article_entity.article_id,
            entity_id=article_entity.entity_id,
            classifier_type=article_entity.classifier_type,
            created_at=article_entity.created_at,
        )

        return ArticleEntity.model_validate(dict(result))
