"""RSS-based article discovery for Jamaica Observer."""

import asyncio
from datetime import datetime, timezone
from typing import Any
import feedparser
import httpx
from loguru import logger

from src.article_discovery.models import DiscoveredArticle, RssFeedConfig
from src.article_discovery.utils import deduplicate_discovered_articles


class JamaicaObserverRssFeedDiscoverer:
    """
    Discovers articles from Jamaica Observer RSS feeds.

    Implements the ArticleDiscovery protocol by fetching and parsing
    the RSS feeds to produce DiscoveredArticle instances.

    Includes exponential backoff retry logic for network failures.
    """

    def __init__(
        self,
        feed_configs: list[RssFeedConfig],
        timeout: int = 30,
        max_retries: int = 3,
        base_backoff: float = 2.0,
    ):
        """
        Initialize the RSS discoverer.

        Args:
            feed_configs: List of RSS feed configurations
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts for network failures
            base_backoff: Base backoff time in seconds (exponential: 2s, 4s, 8s)
        """
        self.feed_configs = feed_configs
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_backoff = base_backoff

        logger.info(
            f"Initialized JamaicaObserverRssFeedDiscoverer: {len(self.feed_configs)} feed(s), "
            f"max_retries={max_retries}"
        )

    async def discover(self, news_source_id: int) -> list[DiscoveredArticle]:
        """
        Discover articles from all configured RSS feeds.

        Args:
            news_source_id: Database ID of the news source (e.g., 2 for Jamaica Observer)

        Returns:
            List of DiscoveredArticle instances with metadata from all RSS feeds,
            deduplicated across feeds

        Raises:
            ValueError: If news_source_id is invalid
        """
        if news_source_id <= 0:
            logger.error(f"Invalid news_source_id: {news_source_id}")
            raise ValueError(f"Invalid news_source_id: {news_source_id}")

        logger.info(
            f"Starting Jamaica Observer article discovery: news_source_id={news_source_id}, "
            f"{len(self.feed_configs)} feed(s)"
        )

        all_articles = []

        for config in self.feed_configs:
            try:
                logger.info(f"Processing feed: {config.url}")
                articles: list[DiscoveredArticle] = await self._discover_from_feed(config, news_source_id)
                all_articles.extend(articles)
                logger.info(
                    f"Found {len(articles)} articles from {config.url} (section: {config.section})"
                )
            except Exception as e:
                logger.exception(
                    f"Failed to process feed {config.url}: {type(e).__name__}: {e}"
                )
                continue

        if not all_articles:
            logger.warning("No articles discovered from any feed")
            return []

        deduplicated_articles = deduplicate_discovered_articles(all_articles)

        duplicates_removed = len(all_articles) - len(deduplicated_articles)
        if duplicates_removed > 0:
            logger.info(
                f"Removed {duplicates_removed} cross-feed duplicate(s) "
                f"(total: {len(all_articles)} → unique: {len(deduplicated_articles)})"
            )

        logger.info(
            f"Discovery complete: {len(deduplicated_articles)} unique articles discovered"
        )

        return deduplicated_articles

    async def _discover_from_feed(
        self, config: RssFeedConfig, news_source_id: int
    ) -> list[DiscoveredArticle]:
        """
        Discover articles from a single RSS feed.

        Args:
            config: RSS feed configuration (URL + section)
            news_source_id: Database ID of news source

        Returns:
            List of discovered articles from this feed

        Raises:
            RuntimeError: If feed fetch/parse fails
        """
        response = await self._fetch_feed_with_retry(config.url)

        logger.debug(f"Parsing RSS feed from {config.url}")
        feed = feedparser.parse(response.content)

        if feed.bozo:
            logger.error(f"Invalid RSS feed format: {feed.bozo_exception}")
            raise RuntimeError(f"Invalid RSS feed format: {feed.bozo_exception}")

        logger.info(
            f"RSS feed parsed successfully: {len(feed.entries)} entries found in {config.url}"
        )

        return self._parse_all_entries(feed.entries, news_source_id, config.section, config.url)

    async def _fetch_feed_with_retry(self, feed_url: str) -> httpx.Response:
        """
        Fetch RSS feed with exponential backoff retry logic.

        Args:
            feed_url: RSS feed URL to fetch

        Returns:
            HTTP response object

        Raises:
            RuntimeError: If all retry attempts fail
        """
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    f"Fetching RSS feed from {feed_url} (attempt {attempt}/{self.max_retries})"
                )
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        feed_url,
                        timeout=self.timeout,
                        headers={
                            "User-Agent": "JaAccountable-Bot/1.0 (Article Discovery Service)"
                        }
                    )
                    response.raise_for_status()
                    logger.debug(
                        f"RSS feed fetched successfully: {len(response.content)} bytes"
                    )
                    return response

            except httpx.HTTPError as e:
                last_exception = e
                logger.warning(
                    f"Failed to fetch RSS feed (attempt {attempt}/{self.max_retries}): {e}"
                )

                if attempt < self.max_retries:
                    backoff_time = self.base_backoff ** attempt  # 2^1=2s, 2^2=4s, 2^3=8s
                    logger.info(f"Retrying in {backoff_time:.1f} seconds...")
                    await asyncio.sleep(backoff_time)

        logger.error(
            f"Failed to fetch RSS feed from {feed_url} after {self.max_retries} attempts"
        )
        raise RuntimeError(
            f"Failed to fetch RSS feed after {self.max_retries} attempts: {last_exception}"
        ) from last_exception

    def _parse_all_entries(
        self, entries: list[Any], news_source_id: int, section: str, feed_url: str
    ) -> list[DiscoveredArticle]:
        """
        Parse all RSS entries into DiscoveredArticle instances.

        Skips malformed entries and logs detailed information about failures.

        Args:
            entries: List of feedparser entry objects
            news_source_id: Database ID of news source
            section: Section name to assign to discovered articles
            feed_url: RSS feed URL (for logging purposes)

        Returns:
            List of successfully parsed DiscoveredArticle instances
        """
        discovered_articles = []
        skipped_count = 0

        for i, entry in enumerate(entries, 1):
            try:
                article = self._parse_rss_entry(entry, news_source_id, section)
                discovered_articles.append(article)
                logger.debug(
                    f"Parsed entry {i}/{len(entries)}: {article.title or article.url}"
                )
            except (KeyError, ValueError, AttributeError) as e:
                skipped_count += 1
                self._log_skipped_entry(entry, i, len(entries), e, feed_url)
                continue

        if skipped_count > 0:
            logger.info(f"Skipped {skipped_count} malformed entries")

        return discovered_articles

    def _parse_rss_entry(
        self, entry: Any, news_source_id: int, section: str
    ) -> DiscoveredArticle:
        """
        Parse a single RSS entry into a DiscoveredArticle.

        Args:
            entry: feedparser entry object
            news_source_id: Database ID of news source
            section: Section name to assign to discovered article

        Returns:
            DiscoveredArticle instance

        Raises:
            KeyError: If required fields are missing
            ValueError: If field values are invalid
            AttributeError: If entry structure is unexpected
        """
        url = entry.link  # Required - will raise AttributeError if missing
        title = entry.get("title", "").strip() or None

        published_date = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            import time as time_module
            timestamp = time_module.mktime(entry.published_parsed)
            published_date = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif hasattr(entry, "published"):
            try:
                from email.utils import parsedate_to_datetime
                published_date = parsedate_to_datetime(entry.published)
                if published_date.tzinfo is None:
                    published_date = published_date.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                logger.debug(f"Could not parse published date: {entry.published}")

        discovered_at = datetime.now(timezone.utc)

        return DiscoveredArticle(
            url=url,
            news_source_id=news_source_id,
            section=section,
            discovered_at=discovered_at,
            title=title,
            published_date=published_date,
        )

    def _log_skipped_entry(
        self, entry: Any, entry_num: int, total_entries: int, error: Exception, feed_url: str
    ) -> None:
        """Log detailed information about a skipped RSS entry."""
        entry_url = getattr(entry, "link", "MISSING")
        entry_title = getattr(entry, "title", "MISSING")
        entry_id = getattr(entry, "id", "MISSING")

        logger.warning(
            f"Skipping malformed RSS entry {entry_num}/{total_entries} from {feed_url}"
        )
        logger.warning(f"  URL: {entry_url}")
        logger.warning(f"  Title: {entry_title}")
        logger.warning(f"  ID: {entry_id}")
        logger.warning(f"  Error: {type(error).__name__}: {error}")
        logger.debug(f"  Raw entry data: {entry}")
