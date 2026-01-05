"""Article discovery service for orchestrating article discovery."""
from datetime import datetime, timezone
import asyncpg
from loguru import logger

from src.article_discovery.models import DiscoveredArticle
from src.article_discovery.base import ArticleDiscoverer
from src.article_persistence.models.domain import NewsSource
from src.article_persistence.repositories.news_source_repository import (
    NewsSourceRepository,
)


class ArticleDiscoveryService:
    """
    Thin service layer for article discovery orchestration.

    This service provides a simple facade over article discoverers,
    focusing on delegation and error handling rather than
    complex orchestration.

    Design Philosophy:
        - Discoverers are created externally and injected
        - Service focuses on delegation, not instantiation
        - Minimal database dependencies
        - Easy to test with dependency injection
        - Multi-strategy support via multiple service calls

    Example Usage (Single Strategy):
        # Create RSS discoverer
        rss_discoverer = GleanerRssFeedDiscoverer(feed_configs=[
            RssFeedConfig(url="https://jamaica-gleaner.com/feed/rss.xml", section="lead-stories"),
        ])

        # Create service
        service = ArticleDiscoveryService(
            discoverer=rss_discoverer,
            news_source_repository=news_source_repository,
        )

        # Discover articles (connection managed by caller)
        async with db_config.connection() as conn:
            articles = await service.discover(conn=conn, news_source_id=1)

    Example Usage (Multi-Strategy):
        # Create RSS service
        rss_discoverer = GleanerRssFeedDiscoverer(feed_configs=rss_feeds)
        rss_service = ArticleDiscoveryService(rss_discoverer, news_source_repository)

        # Create Archive service
        archive_discoverer = GleanerArchiveDiscoverer(base_url="https://jamaica-gleaner.com")
        archive_service = ArticleDiscoveryService(archive_discoverer, news_source_repository)

        # Discover from both strategies (connection managed by caller)
        async with db_config.connection() as conn:
            rss_articles = await rss_service.discover(conn, news_source_id=1)
            archive_articles = await archive_service.discover(conn, news_source_id=1)

        # Merge and deduplicate in calling code
        all_articles = merge_and_deduplicate([rss_articles, archive_articles])
    """

    def __init__(
        self,
        discoverer: ArticleDiscoverer,
        news_source_repository: NewsSourceRepository,
    ):
        """
        Initialize the discovery service.

        Args:
            discoverer: The article discoverer to use
            news_source_repository: Repository for updating news source state
        """
        self.discoverer = discoverer
        self.news_source_repository = news_source_repository

    async def discover(
        self, conn: asyncpg.Connection, news_source_id: int
    ) -> list[DiscoveredArticle]:
        """
        Discover articles from a news source.

        Args:
            conn: Database connection (managed by caller)
            news_source_id: Database ID of the news source

        Returns:
            List of discovered articles

        Raises:
            ValueError: If news_source_id is invalid
            RuntimeError: If discovery fails
        """
        try:
            # Delegate to discoverer
            articles: list[DiscoveredArticle] = await self.discoverer.discover(news_source_id)

            logger.info(
                f"Discovered {len(articles)} articles from source {news_source_id}"
            )

            # Update last_scraped_at timestamp
            updated_news_source = await self._update_last_scraped_at(conn, news_source_id)
            logger.debug(f"{updated_news_source.name} last_scraped_at updated to {updated_news_source.last_scraped_at}")

            return articles

        except ValueError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            # Wrap other errors in RuntimeError for consistent API
            logger.error(f"Discovery failed for source {news_source_id}: {e}")
            raise RuntimeError(
                f"Discovery failed for source {news_source_id}: {e}"
            ) from e

    async def _update_last_scraped_at(
        self, conn: asyncpg.Connection, news_source_id: int
    ) -> NewsSource:
        """Update last_scraped_at timestamp for a news source via repository."""
        updated_news_source: NewsSource = await self.news_source_repository.update_last_scraped_at(
            conn=conn,
            news_source_id=news_source_id,
            last_scraped_at=datetime.now(timezone.utc),
        )
        logger.debug(f"Updated last_scraped_at for source {news_source_id}")
        return updated_news_source
