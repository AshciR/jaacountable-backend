"""Jamaica Observer sitemap-based article discoverer."""

import asyncio
import re
from datetime import datetime, timedelta, timezone
from lxml import etree

import httpx
from loguru import logger

from src.article_discovery.models import DiscoveredArticle
from src.article_discovery.utils import deduplicate_discovered_articles

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_POST_SITEMAP_RE = re.compile(r"post-sitemap(\d+)\.xml$")
_URL_DATE_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/([^/]+)/")


class JamaicaObserverSitemapDiscoverer:
    """
    Discovers articles from Jamaica Observer sitemaps.

    Fetches the WordPress sitemap index at jamaicaobserver.com/sitemap.xml,
    identifies relevant post-sitemap{N}.xml files by lastmod date, then
    fetches each sitemap to extract article URLs filtered by published date.

    Implements the ArticleDiscoverer protocol.

    URL Pattern:
        https://www.jamaicaobserver.com/{YYYY}/{MM}/{DD}/{slug}/

    Discovery Strategy:
        1. Fetch & parse sitemap index
        2. Filter to post-sitemap{N}.xml files within date range (+ buffer)
        3. For each sitemap: fetch, parse URLs, filter by date from URL path
        4. Deduplicate and return

    Example:
        discoverer = JamaicaObserverSitemapDiscoverer(
            start_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2021, 1, 1, tzinfo=timezone.utc),
        )
        articles = await discoverer.discover(news_source_id=2)
    """

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        sitemap_index_url: str = "https://www.jamaicaobserver.com/sitemap.xml",
        timeout: int = 30,
        max_retries: int = 3,
        base_backoff: float = 2.0,
        crawl_delay: float = 1.5,
        sitemap_buffer_days: int = 14,
    ):
        """
        Initialize the Jamaica Observer sitemap discoverer.

        Args:
            start_date: Start of date range (inclusive). Must be timezone-aware.
            end_date: End of date range (inclusive). Must be timezone-aware.
            sitemap_index_url: URL of the sitemap index file.
            timeout: HTTP request timeout in seconds.
            max_retries: Maximum retry attempts for failed requests.
            base_backoff: Base for exponential backoff (seconds).
            crawl_delay: Delay between sitemap fetches (seconds).
            sitemap_buffer_days: Extra days on each side when filtering sitemaps
                by lastmod to avoid missing edge articles.
        """
        if start_date.tzinfo is None:
            raise ValueError("start_date must be timezone-aware")
        if end_date.tzinfo is None:
            raise ValueError("end_date must be timezone-aware")
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")

        self.start_date = start_date
        self.end_date = end_date
        self.sitemap_index_url = sitemap_index_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.crawl_delay = crawl_delay
        self.sitemap_buffer_days = sitemap_buffer_days

        # Populated during discover() — sitemaps that failed after all retries
        self.failed_sitemaps: list[str] = []

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        logger.info(
            f"Initialized JamaicaObserverSitemapDiscoverer: "
            f"{start_date.date()} to {end_date.date()}, "
            f"crawl_delay={crawl_delay}s, buffer={sitemap_buffer_days}d"
        )

    async def discover(self, news_source_id: int) -> list[DiscoveredArticle]:
        """
        Discover articles from Jamaica Observer sitemaps.

        Implements the ArticleDiscoverer protocol.

        Args:
            news_source_id: Database ID of the news source (2 for Jamaica Observer).

        Returns:
            List of deduplicated DiscoveredArticle instances.

        Raises:
            ValueError: If news_source_id is invalid.
            RuntimeError: If the sitemap index cannot be fetched.
        """
        if news_source_id <= 0:
            raise ValueError(f"news_source_id must be positive, got: {news_source_id}")

        self.failed_sitemaps = []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=self.headers,
        ) as client:
            # Step 1: Fetch and parse sitemap index
            sitemap_urls = await self._fetch_sitemap_index(client)
            logger.info(
                f"Found {len(sitemap_urls)} relevant post-sitemaps to process"
            )

            # Step 2: Fetch each sitemap and extract articles
            discovered_at = datetime.now(timezone.utc)
            all_articles: list[DiscoveredArticle] = []

            for i, sitemap_url in enumerate(sitemap_urls):
                # Crawl delay before each fetch (skip before first)
                if i > 0:
                    logger.debug(f"Crawl delay: {self.crawl_delay}s")
                    await asyncio.sleep(self.crawl_delay)

                sitemap_name = sitemap_url.split("/")[-1]
                try:
                    articles = await self._fetch_sitemap_articles(
                        client, sitemap_url, news_source_id, discovered_at
                    )
                    all_articles.extend(articles)
                except Exception as e:
                    logger.error(
                        f"Failed to process {sitemap_name} after all retries: {e}"
                    )
                    self.failed_sitemaps.append(sitemap_name)

        # Step 3: Deduplicate
        unique_articles = deduplicate_discovered_articles(all_articles)
        logger.info(
            f"Discovery complete: {len(unique_articles)} unique articles "
            f"from {len(sitemap_urls)} sitemaps "
            f"({len(self.failed_sitemaps)} failed)"
        )

        return unique_articles

    async def _fetch_sitemap_index(self, client: httpx.AsyncClient) -> list[str]:
        """
        Fetch and parse the sitemap index, returning relevant post-sitemap URLs.

        Filters to post-sitemap{N}.xml files whose lastmod falls within
        [start_date - buffer, end_date + buffer]. Sorted numerically by N.

        Args:
            client: HTTP client.

        Returns:
            Sorted list of sitemap URLs to process.

        Raises:
            RuntimeError: If the index cannot be fetched or parsed.
        """
        logger.info(f"Fetching sitemap index: {self.sitemap_index_url}")
        xml = await self._fetch_with_retry(client, self.sitemap_index_url)

        root = etree.fromstring(xml.encode("utf-8"))
        ns = _SITEMAP_NS

        buffered_start = self.start_date - timedelta(days=self.sitemap_buffer_days)
        buffered_end = self.end_date + timedelta(days=self.sitemap_buffer_days)

        relevant: list[tuple[int, str]] = []  # (N, url)

        for sitemap_el in root.findall(f"{{{ns}}}sitemap"):
            loc_el = sitemap_el.find(f"{{{ns}}}loc")
            lastmod_el = sitemap_el.find(f"{{{ns}}}lastmod")

            if loc_el is None or not loc_el.text:
                continue

            loc = loc_el.text.strip()
            match = _POST_SITEMAP_RE.search(loc)
            if not match:
                continue  # skip page-sitemap* and others

            n = int(match.group(1))

            # Filter by lastmod if available
            if lastmod_el is not None and lastmod_el.text:
                lastmod = self._parse_lastmod(lastmod_el.text.strip())
                if lastmod is not None:
                    if lastmod < buffered_start or lastmod > buffered_end:
                        continue

            relevant.append((n, loc))

        # Sort by sitemap number
        relevant.sort(key=lambda x: x[0])
        urls = [url for _, url in relevant]

        logger.info(
            f"Sitemap index parsed: {len(urls)} post-sitemaps in range "
            f"[{buffered_start.date()} — {buffered_end.date()}]"
        )
        return urls

    async def _fetch_sitemap_articles(
        self,
        client: httpx.AsyncClient,
        sitemap_url: str,
        news_source_id: int,
        discovered_at: datetime,
    ) -> list[DiscoveredArticle]:
        """
        Fetch a single post-sitemap XML and extract articles within the date range.

        Args:
            client: HTTP client.
            sitemap_url: URL of the post-sitemap XML.
            news_source_id: Database ID of the news source.
            discovered_at: Timestamp to use for all articles in this batch.

        Returns:
            List of DiscoveredArticle instances in the target date range.
        """
        sitemap_name = sitemap_url.split("/")[-1]
        xml = await self._fetch_with_retry(client, sitemap_url)

        root = etree.fromstring(xml.encode("utf-8"))
        ns = _SITEMAP_NS

        total = 0
        in_range = 0
        articles: list[DiscoveredArticle] = []

        for url_el in root.findall(f"{{{ns}}}url"):
            loc_el = url_el.find(f"{{{ns}}}loc")
            if loc_el is None or not loc_el.text:
                continue

            loc = loc_el.text.strip()
            total += 1

            published_date = self._parse_date_from_url(loc)
            if published_date is None:
                logger.debug(f"Could not parse date from URL, skipping: {loc}")
                continue

            if published_date < self.start_date or published_date > self.end_date:
                continue

            slug = self._parse_slug_from_url(loc)

            articles.append(
                DiscoveredArticle(
                    url=loc,
                    news_source_id=news_source_id,
                    section="archive",
                    discovered_at=discovered_at,
                    title=slug,
                    published_date=published_date,
                )
            )
            in_range += 1

        logger.info(
            f"Fetched {sitemap_name} — {total} URLs found, {in_range} in date range"
        )
        return articles

    async def _fetch_with_retry(self, client: httpx.AsyncClient, url: str) -> str:
        """
        Fetch a URL with exponential backoff retry logic.

        Args:
            client: HTTP client.
            url: URL to fetch.

        Returns:
            Response text.

        Raises:
            httpx.HTTPStatusError: If all retry attempts fail with HTTP error.
            httpx.RequestError: If all retry attempts fail with network error.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.text

            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if attempt == self.max_retries:
                    logger.error(
                        f"Failed to fetch {url} after {self.max_retries} attempts: {e}"
                    )
                    raise

                backoff = self.base_backoff ** attempt
                logger.warning(
                    f"Attempt {attempt}/{self.max_retries} failed for {url}, "
                    f"retrying in {backoff}s: {e}"
                )
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Failed to fetch {url} after {self.max_retries} attempts")

    def _parse_lastmod(self, lastmod_str: str) -> datetime | None:
        """
        Parse a lastmod string into a timezone-aware datetime.

        Handles ISO 8601 formats: YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS+HH:MM, etc.

        Args:
            lastmod_str: Raw lastmod string from sitemap XML.

        Returns:
            Timezone-aware datetime, or None if parsing fails.
        """
        # Try date-only format first (YYYY-MM-DD)
        try:
            dt = datetime.strptime(lastmod_str[:10], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            return dt
        except ValueError:
            pass

        # Try full ISO 8601 with fromisoformat
        try:
            dt = datetime.fromisoformat(lastmod_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            logger.debug(f"Could not parse lastmod: {lastmod_str!r}")
            return None

    def _parse_date_from_url(self, url: str) -> datetime | None:
        """
        Extract published date from Jamaica Observer URL path.

        URL pattern: /{YYYY}/{MM}/{DD}/{slug}/

        Args:
            url: Article URL.

        Returns:
            Timezone-aware datetime at midnight UTC, or None if not found.
        """
        match = _URL_DATE_RE.search(url)
        if not match:
            return None

        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            logger.debug(f"Invalid date in URL {url}: {year}-{month:02d}-{day:02d}")
            return None

    def _parse_slug_from_url(self, url: str) -> str | None:
        """
        Extract article slug from Jamaica Observer URL path.

        The slug is the last non-empty path segment before the trailing slash.

        Args:
            url: Article URL.

        Returns:
            Slug string, or None if not found.
        """
        match = _URL_DATE_RE.search(url)
        if not match:
            return None
        return match.group(4)
