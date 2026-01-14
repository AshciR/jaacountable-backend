"""Repository for article database operations."""
import aiosql
from pathlib import Path
from uuid import UUID

import asyncpg

from src.article_persistence.models.domain import Article


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
            news_source_id=article.news_source_id,
        )

        # Convert asyncpg.Record to Article model
        # Note: SQL query doesn't return full_text for performance,
        # so we use the original article's full_text value
        return Article(
            id=result['id'],
            public_id=result['public_id'],
            url=result['url'],
            title=result['title'],
            section=result['section'],
            published_date=result['published_date'],
            fetched_at=result['fetched_at'],
            full_text=article.full_text,
            news_source_id=result['news_source_id'],
        )

    async def get_existing_urls(
        self,
        conn: asyncpg.Connection,
        urls: list[str],
    ) -> set[str]:
        """
        Check which URLs from a list already exist in the database.

        Uses a single batch query for performance (60x-600x faster than
        individual queries for large batches).

        Args:
            conn: Database connection to use for the query
            urls: List of URLs to check

        Returns:
            Set of URLs that already exist in the database

        Example:
            >>> repo = ArticleRepository()
            >>> async with db_config.connection() as conn:
            ...     existing = await repo.get_existing_urls(
            ...         conn,
            ...         ["https://example.com/1", "https://example.com/2"]
            ...     )
            ...     print(existing)  # {"https://example.com/1"}
        """
        if not urls:
            return set()

        # Query using aiosql with PostgreSQL array syntax
        rows = await self.queries.get_existing_urls(conn, urls=urls)

        # Extract URLs from rows and return as set
        return {row["url"] for row in rows}

    async def get_by_public_id(
        self,
        conn: asyncpg.Connection,
        public_id: UUID,
    ) -> Article | None:
        """
        Retrieve an article by its public UUID.

        Args:
            conn: Database connection to use for the query
            public_id: The public UUID of the article

        Returns:
            Article if found, None otherwise
        """
        result = await self.queries.get_article_by_public_id(
            conn, public_id=public_id
        )
        if result is None:
            return None

        return Article(
            id=result['id'],
            public_id=result['public_id'],
            url=result['url'],
            title=result['title'],
            section=result['section'],
            published_date=result['published_date'],
            fetched_at=result['fetched_at'],
            full_text=result['full_text'],
            news_source_id=result['news_source_id'],
        )
