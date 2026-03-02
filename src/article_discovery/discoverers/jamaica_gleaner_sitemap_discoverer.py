"""Jamaica Gleaner sitemap-based article discoverer."""

import asyncio
import re
from datetime import datetime, timezone
from lxml import etree

import httpx
from loguru import logger

from src.article_discovery.models import DiscoveredArticle
from src.article_discovery.utils import deduplicate_discovered_articles

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_SITEMAPINDEX_TAG = f"{{{_SITEMAP_NS}}}sitemapindex"
_URLSET_TAG = f"{{{_SITEMAP_NS}}}urlset"
_SITEMAP_PAGE_RE = re.compile(r"sitemap\.xml\?page=(\d+)$")
_URL_RE = re.compile(r"/article/([^/]+)/(\d{4})(\d{2})(\d{2})/([^/]+)")


class JamaicaGleanerSitemapDiscoverer:
    """
    Discovers articles from Jamaica Gleaner sitemaps.

    Fetches the Drupal sitemap at jamaica-gleaner.com/sitemap.xml and handles
    two possible formats:

    - **sitemapindex**: The root is <sitemapindex> with child <sitemap> entries
      pointing to paginated pages (sitemap.xml?page=N). Each page is fetched
      and its article URLs are extracted.

    - **urlset**: The root is <urlset> with all article <url> entries directly.
      This is the single-page format Drupal uses when the sitemap fits on one
      chunk.

    Both formats are detected automatically from the root XML element.

    Implements the ArticleDiscoverer protocol.

    URL Pattern:
        https://jamaica-gleaner.com/article/{section}/{YYYYMMDD}/{slug}

    Discovery Strategy:
        1. Fetch sitemap index URL
        2. Detect format (sitemapindex vs urlset)
        3. If sitemapindex: collect all ?page=N URLs (sorted), fetch each with
           crawl delay, extract articles filtered by date
        4. If urlset: extract articles directly from the root document
        5. Deduplicate and return

    Example:
        discoverer = JamaicaGleanerSitemapDiscoverer(
            start_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
        )
        articles = await discoverer.discover(news_source_id=1)
    """

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        sitemap_index_url: str = "https://jamaica-gleaner.com/sitemap.xml",
        timeout: int = 30,
        max_retries: int = 3,
        base_backoff: float = 2.0,
        crawl_delay: float = 1.5,
    ):
        """
        Initialize the Jamaica Gleaner sitemap discoverer.

        Args:
            start_date: Start of date range (inclusive). Must be timezone-aware.
            end_date: End of date range (inclusive). Must be timezone-aware.
            sitemap_index_url: URL of the sitemap (index or direct urlset).
            timeout: HTTP request timeout in seconds.
            max_retries: Maximum retry attempts for failed requests.
            base_backoff: Base for exponential backoff (seconds).
            crawl_delay: Delay between sitemap page fetches (seconds).
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

        # Populated during discover() — pages that failed after all retries
        self.failed_sitemaps: list[str] = []

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        logger.info(
            f"Initialized JamaicaGleanerSitemapDiscoverer: "
            f"{start_date.date()} to {end_date.date()}, "
            f"crawl_delay={crawl_delay}s"
        )

    async def discover(self, news_source_id: int) -> list[DiscoveredArticle]:
        """
        Discover articles from Jamaica Gleaner sitemaps.

        Implements the ArticleDiscoverer protocol.

        Args:
            news_source_id: Database ID of the news source (1 for Jamaica Gleaner).

        Returns:
            List of deduplicated DiscoveredArticle instances.

        Raises:
            ValueError: If news_source_id is invalid.
            RuntimeError: If the sitemap index cannot be fetched.
        """
        if news_source_id <= 0:
            raise ValueError(f"news_source_id must be positive, got: {news_source_id}")

        self.failed_sitemaps = []
        discovered_at = datetime.now(timezone.utc)
        all_articles: list[DiscoveredArticle] = []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=self.headers,
            http2=False,
        ) as client:
            # Step 1: Fetch the sitemap root document
            logger.info(f"Fetching sitemap: {self.sitemap_index_url}")
            xml = await self._fetch_with_retry(client, self.sitemap_index_url)
            root = etree.fromstring(xml.encode("utf-8"))

            # Step 2: Detect format and extract articles
            if root.tag == _SITEMAPINDEX_TAG:
                # Multi-page: fetch each page separately
                page_urls = self._extract_page_urls(root)
                logger.info(f"Sitemap index: {len(page_urls)} pages to process")

                for i, page_url in enumerate(page_urls):
                    if i > 0:
                        logger.debug(f"Crawl delay: {self.crawl_delay}s")
                        await asyncio.sleep(self.crawl_delay)

                    page_name = page_url.split("?")[-1]
                    try:
                        articles = await self._fetch_sitemap_articles(
                            client, page_url, news_source_id, discovered_at
                        )
                        all_articles.extend(articles)
                    except Exception as e:
                        logger.error(
                            f"Failed to process {page_name} after all retries: {e}"
                        )
                        self.failed_sitemaps.append(page_name)

            elif root.tag == _URLSET_TAG:
                # Single-page: all articles are in this document
                logger.info("Sitemap is a single urlset — extracting articles directly")
                articles = self._extract_articles_from_urlset(
                    root, news_source_id, discovered_at
                )
                all_articles.extend(articles)

            else:
                raise RuntimeError(
                    f"Unexpected sitemap root element: {root.tag!r}"
                )

        # Step 3: Deduplicate
        unique_articles = deduplicate_discovered_articles(all_articles)
        logger.info(
            f"Discovery complete: {len(unique_articles)} unique articles "
            f"({len(self.failed_sitemaps)} failed pages)"
        )

        return unique_articles

    def _extract_page_urls(self, root: etree._Element) -> list[str]:
        """
        Extract sitemap page URLs from a sitemapindex root element.

        Filters to sitemap.xml?page=N entries and sorts by page number.

        Args:
            root: Parsed sitemapindex XML root.

        Returns:
            Sorted list of page URLs.
        """
        ns = _SITEMAP_NS
        relevant: list[tuple[int, str]] = []

        for sitemap_el in root.findall(f"{{{ns}}}sitemap"):
            loc_el = sitemap_el.find(f"{{{ns}}}loc")
            if loc_el is None or not loc_el.text:
                continue

            loc = loc_el.text.strip()
            match = _SITEMAP_PAGE_RE.search(loc)
            if not match:
                continue

            page_num = int(match.group(1))
            relevant.append((page_num, loc))

        relevant.sort(key=lambda x: x[0])
        return [url for _, url in relevant]

    def _extract_articles_from_urlset(
        self,
        root: etree._Element,
        news_source_id: int,
        discovered_at: datetime,
    ) -> list[DiscoveredArticle]:
        """
        Extract articles from a urlset root element, filtering by date range.

        Args:
            root: Parsed urlset XML root.
            news_source_id: Database ID of the news source.
            discovered_at: Timestamp for all articles in this batch.

        Returns:
            List of DiscoveredArticle instances in the target date range.
        """
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

            section = self._parse_section_from_url(loc)
            if section != "news":
                continue

            slug = self._parse_slug_from_url(loc)

            articles.append(
                DiscoveredArticle(
                    url=loc,
                    news_source_id=news_source_id,
                    section=section,
                    discovered_at=discovered_at,
                    title=slug,
                    published_date=published_date,
                )
            )
            in_range += 1

        logger.info(f"urlset — {total} URLs found, {in_range} in date range")
        return articles

    async def _fetch_sitemap_articles(
        self,
        client: httpx.AsyncClient,
        page_url: str,
        news_source_id: int,
        discovered_at: datetime,
    ) -> list[DiscoveredArticle]:
        """
        Fetch a single sitemap page and extract articles within the date range.

        Args:
            client: HTTP client.
            page_url: URL of the sitemap page.
            news_source_id: Database ID of the news source.
            discovered_at: Timestamp to use for all articles in this batch.

        Returns:
            List of DiscoveredArticle instances in the target date range.
        """
        page_name = page_url.split("?")[-1]
        xml = await self._fetch_with_retry(client, page_url)
        root = etree.fromstring(xml.encode("utf-8"))

        articles = self._extract_articles_from_urlset(root, news_source_id, discovered_at)
        logger.info(f"Page {page_name}: {len(articles)} articles in date range")
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

    def _parse_date_from_url(self, url: str) -> datetime | None:
        """
        Extract published date from Jamaica Gleaner URL path.

        URL pattern: /article/{section}/{YYYYMMDD}/{slug}

        Args:
            url: Article URL.

        Returns:
            Timezone-aware datetime at midnight UTC, or None if not found.
        """
        match = _URL_RE.search(url)
        if not match:
            return None

        year, month, day = int(match.group(2)), int(match.group(3)), int(match.group(4))
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            logger.debug(f"Invalid date in URL {url}: {year}-{month:02d}-{day:02d}")
            return None

    def _parse_section_from_url(self, url: str) -> str | None:
        """
        Extract section from Jamaica Gleaner URL path.

        The section is the path segment immediately after /article/.

        Args:
            url: Article URL.

        Returns:
            Section string (e.g. 'news', 'sports'), or None if not found.
        """
        match = _URL_RE.search(url)
        if not match:
            return None
        return match.group(1)

    def _parse_slug_from_url(self, url: str) -> str | None:
        """
        Extract article slug from Jamaica Gleaner URL path.

        The slug is the last path segment after the date.

        Args:
            url: Article URL.

        Returns:
            Slug string, or None if not found.
        """
        match = _URL_RE.search(url)
        if not match:
            return None
        return match.group(5)
