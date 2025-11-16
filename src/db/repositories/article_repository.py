"""Repository for article database operations."""
import aiosql
from datetime import datetime
from pathlib import Path
import asyncpg

from src.db.models.domain import Article


class ArticleRepository:
    """Repository for article database operations using aiosql."""

    def __init__(self):
        """Initialize the repository and load SQL queries."""
        # Load queries from the queries directory
        queries_path = Path(__file__).parent.parent / "queries"
        self.queries = aiosql.from_path(str(queries_path), "asyncpg")

    async def insert_article(
        self,
        conn: asyncpg.Connection,
        article: Article,
    ) -> Article:
        """
        Insert a new article into the database.

        Args:
            conn: Database connection to use for the query
            article: Article model with validated data

        Returns:
            Article: The inserted article with database-generated id

        Raises:
            asyncpg.UniqueViolationError: If article URL already exists
            ValueError: If article data fails validation
        """
        # Article model handles validation and provides fetched_at default
        result = await self.queries.insert_article(
            conn,
            url=article.url,
            title=article.title,
            section=article.section,
            published_date=article.published_date,
            fetched_at=article.fetched_at,
            full_text=article.full_text,
        )

        # Convert asyncpg.Record to Article model
        # Note: SQL query doesn't return full_text for performance,
        # so we use the original article's full_text value
        return Article(
            id=result['id'],
            url=result['url'],
            title=result['title'],
            section=result['section'],
            published_date=result['published_date'],
            fetched_at=result['fetched_at'],
            full_text=article.full_text,
        )
