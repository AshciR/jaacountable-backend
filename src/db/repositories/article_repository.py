"""Repository for article database operations."""
import aiosql
from datetime import datetime
from pathlib import Path
import asyncpg


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
        url: str,
        title: str,
        section: str,
        published_date: datetime | None = None,
        fetched_at: datetime | None = None,
        full_text: str | None = None
    ) -> asyncpg.Record:
        """
        Insert a new article into the database.

        Args:
            conn: Database connection to use for the query
            url: Article URL (must be unique)
            title: Article title
            section: Article section (e.g., "lead-stories", "news")
            published_date: When the article was published (optional)
            fetched_at: When the article was scraped (defaults to now)
            full_text: Full article content (optional)

        Returns:
            asyncpg.Record: The inserted article record with id, url, title,
                           section, published_date, and fetched_at

        Raises:
            asyncpg.UniqueViolationError: If article URL already exists
        """
        if fetched_at is None:
            fetched_at = datetime.now()

        result = await self.queries.insert_article(
            conn,
            url=url,
            title=title,
            section=section,
            published_date=published_date,
            fetched_at=fetched_at,
            full_text=full_text
        )
        return result
