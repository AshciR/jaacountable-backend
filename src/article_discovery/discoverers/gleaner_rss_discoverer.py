"""RSS-based article discovery for Jamaica Gleaner."""

import logging
import time
from datetime import datetime, timezone
from typing import Any
import feedparser
import requests
from src.article_discovery.models import DiscoveredArticle

logger = logging.getLogger(__name__)


class GleanerRssFeedDiscoverer:
    """
    Discovers articles from Jamaica Gleaner RSS feed.

    Implements the ArticleDiscovery protocol by fetching and parsing
    the RSS feed to produce DiscoveredArticle instances.

    Includes exponential backoff retry logic for network failures.
    """

    def __init__(
        self,
        feed_url: str = "https://jamaica-gleaner.com/feed/rss.xml",
        section: str = "lead-stories",
        timeout: int = 30,
        max_retries: int = 3,
        base_backoff: float = 2.0,
    ):
        """
        Initialize the RSS discoverer.

        Args:
            feed_url: RSS feed URL
            section: Section name to assign to discovered articles
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts for network failures
            base_backoff: Base backoff time in seconds (exponential: 2s, 4s, 8s)
        """
        self.feed_url = feed_url
        self.section = section
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        logger.info(
            f"Initialized GleanerRssFeedDiscoverer: feed_url={feed_url}, "
            f"section={section}, max_retries={max_retries}"
        )

    async def discover(self, news_source_id: int) -> list[DiscoveredArticle]:
        """
        Discover articles from RSS feed.

        Args:
            news_source_id: Database ID of the news source (e.g., 1 for Jamaica Gleaner)

        Returns:
            List of DiscoveredArticle instances with metadata from RSS feed

        Raises:
            ValueError: If news_source_id is invalid
            RuntimeError: If feed fetch/parse fails after all retries
        """
        # Validate input
        if news_source_id <= 0:
            logger.error(f"Invalid news_source_id: {news_source_id}")
            raise ValueError(f"Invalid news_source_id: {news_source_id}")

        logger.info(
            f"Starting article discovery: news_source_id={news_source_id}, "
            f"feed_url={self.feed_url}"
        )

        # Fetch RSS feed with retry logic
        response = self._fetch_feed_with_retry()

        # Parse RSS feed
        logger.debug("Parsing RSS feed")
        feed = feedparser.parse(response.content)

        if feed.bozo:  # feedparser sets bozo=1 if feed has errors
            logger.error(f"Invalid RSS feed format: {feed.bozo_exception}")
            raise RuntimeError(f"Invalid RSS feed format: {feed.bozo_exception}")

        logger.info(f"RSS feed parsed successfully: {len(feed.entries)} entries found")

        # Parse all entries into DiscoveredArticle instances
        discovered_articles = self._parse_all_entries(feed.entries, news_source_id)

        # Deduplicate by URL (in case feed has duplicates)
        deduplicated_articles = self._deduplicate_articles(discovered_articles)

        duplicates_removed = len(discovered_articles) - len(deduplicated_articles)
        if duplicates_removed > 0:
            logger.info(f"Removed {duplicates_removed} duplicate URLs from feed")

        logger.info(
            f"Discovery complete: {len(deduplicated_articles)} unique articles discovered"
        )

        return deduplicated_articles

    def _fetch_feed_with_retry(self) -> requests.Response:
        """
        Fetch RSS feed with exponential backoff retry logic.

        Returns:
            HTTP response object

        Raises:
            RuntimeError: If all retry attempts fail
        """
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    f"Fetching RSS feed from {self.feed_url} (attempt {attempt}/{self.max_retries})"
                )
                response = requests.get(
                    self.feed_url,
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

            except requests.RequestException as e:
                last_exception = e
                logger.warning(
                    f"Failed to fetch RSS feed (attempt {attempt}/{self.max_retries}): {e}"
                )

                # Don't sleep after the last attempt
                if attempt < self.max_retries:
                    backoff_time = self.base_backoff ** attempt  # 2^1=2s, 2^2=4s, 2^3=8s
                    logger.info(
                        f"Retrying in {backoff_time:.1f} seconds..."
                    )
                    time.sleep(backoff_time)

        # All retries failed
        logger.error(
            f"Failed to fetch RSS feed from {self.feed_url} after {self.max_retries} attempts"
        )
        raise RuntimeError(
            f"Failed to fetch RSS feed after {self.max_retries} attempts: {last_exception}"
        ) from last_exception

    def _parse_all_entries(
        self, entries: list[Any], news_source_id: int
    ) -> list[DiscoveredArticle]:
        """
        Parse all RSS entries into DiscoveredArticle instances.

        Skips malformed entries and logs detailed information about failures.

        Args:
            entries: List of feedparser entry objects
            news_source_id: Database ID of news source

        Returns:
            List of successfully parsed DiscoveredArticle instances
        """
        discovered_articles = []
        skipped_count = 0

        for i, entry in enumerate(entries, 1):
            try:
                article = self._parse_rss_entry(entry, news_source_id)
                discovered_articles.append(article)
                logger.debug(
                    f"Parsed entry {i}/{len(entries)}: {article.title or article.url}"
                )
            except (KeyError, ValueError, AttributeError) as e:
                # Log detailed information about skipped entry
                skipped_count += 1
                self._log_skipped_entry(entry, i, len(entries), e)
                continue

        if skipped_count > 0:
            logger.info(f"Skipped {skipped_count} malformed entries")

        return discovered_articles

    def _log_skipped_entry(
        self, entry: Any, entry_num: int, total_entries: int, error: Exception
    ) -> None:
        """
        Log detailed information about a skipped RSS entry.

        Args:
            entry: The feedparser entry that was skipped
            entry_num: Entry number in feed
            total_entries: Total number of entries in feed
            error: The exception that caused the skip
        """
        # Extract available information from entry
        entry_url = getattr(entry, "link", "MISSING")
        entry_title = getattr(entry, "title", "MISSING")
        entry_id = getattr(entry, "id", "MISSING")

        # Log warning with context
        logger.warning(
            f"Skipping malformed RSS entry {entry_num}/{total_entries} from {self.feed_url}"
        )
        logger.warning(f"  URL: {entry_url}")
        logger.warning(f"  Title: {entry_title}")
        logger.warning(f"  ID: {entry_id}")
        logger.warning(f"  Error: {type(error).__name__}: {error}")

        # Log raw entry data for debugging (at debug level)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"  Raw entry data: {entry}")

    def _parse_rss_entry(self, entry: Any, news_source_id: int) -> DiscoveredArticle:
        """
        Parse a single RSS entry into a DiscoveredArticle.

        Args:
            entry: feedparser entry object
            news_source_id: Database ID of news source

        Returns:
            DiscoveredArticle instance

        Raises:
            KeyError: If required fields are missing
            ValueError: If field values are invalid
            AttributeError: If entry structure is unexpected
        """
        # Extract required fields
        url = entry.link  # Required - will raise AttributeError if missing
        title = entry.get("title", "").strip() or None  # Optional

        # Parse published date (RSS uses 'published' or 'published_parsed')
        published_date = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            # Convert time.struct_time to timezone-aware datetime
            import time as time_module
            timestamp = time_module.mktime(entry.published_parsed)
            published_date = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif hasattr(entry, "published"):
            # Try parsing ISO 8601 or RFC 822 date string
            try:
                from email.utils import parsedate_to_datetime
                published_date = parsedate_to_datetime(entry.published)
                # Ensure UTC timezone
                if published_date.tzinfo is None:
                    published_date = published_date.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                logger.debug(f"Could not parse published date: {entry.published}")

        # Discovered timestamp is now
        discovered_at = datetime.now(timezone.utc)

        return DiscoveredArticle(
            url=url,
            news_source_id=news_source_id,
            section=self.section,  # Use parameterized section
            discovered_at=discovered_at,
            title=title,
            published_date=published_date,
        )

    def _deduplicate_articles(
        self, articles: list[DiscoveredArticle]
    ) -> list[DiscoveredArticle]:
        """
        Remove duplicate URLs from article list.

        Keeps the first occurrence of each URL.

        Args:
            articles: List of discovered articles

        Returns:
            Deduplicated list (first occurrence kept)
        """
        seen_urls = set()
        unique_articles = []

        for article in articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)

        return unique_articles
