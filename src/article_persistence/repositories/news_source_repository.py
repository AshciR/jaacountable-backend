"""Repository for news source database operations."""
from datetime import datetime

import aiosql
from pathlib import Path
import asyncpg

from src.article_persistence.models.domain import NewsSource


class NewsSourceRepository:
    """Repository for news source database operations using aiosql."""

    def __init__(self):
        """Initialize the repository and load SQL queries."""
        # Load queries from the queries directory
        queries_path = Path(__file__).parent.parent / "queries"
        self.queries = aiosql.from_path(str(queries_path), "asyncpg")

    async def insert_news_source(
        self,
        conn: asyncpg.Connection,
        news_source: NewsSource,
    ) -> NewsSource:
        """
        Insert a new news source into the database.

        Args:
            conn: Database connection to use for the query
            news_source: NewsSource model with validated data

        Returns:
            NewsSource: The inserted news source with database-generated id

        Raises:
            asyncpg.UniqueViolationError: If news source name already exists
            ValueError: If news source data fails validation
        """
        result = await self.queries.insert_news_source(
            conn,
            name=news_source.name,
            base_url=news_source.base_url,
            crawl_delay=news_source.crawl_delay,
            is_active=news_source.is_active,
            last_scraped_at=news_source.last_scraped_at,
            created_at=news_source.created_at,
        )

        return NewsSource.model_validate(dict(result))

    async def update_last_scraped_at(
        self,
        conn: asyncpg.Connection,
        news_source_id: int,
        last_scraped_at: datetime,
    ) -> NewsSource:
        """
        Update the last_scraped_at timestamp for a news source.

        Args:
            conn: Database connection to use for the query
            news_source_id: ID of the news source to update
            last_scraped_at: Timestamp to set for last_scraped_at

        Returns:
            NewsSource: The updated news source record

        Raises:
            asyncpg.PostgresError: If database operation fails
        """
        result = await self.queries.update_last_scraped_at(
            conn,
            id=news_source_id,
            last_scraped_at=last_scraped_at,
        )

        return NewsSource.model_validate(dict(result))
