"""Jamaica Observer daily archive page discoverer."""

import asyncio
import re
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from src.article_discovery.models import DiscoveredArticle
from src.article_discovery.utils import deduplicate_discovered_articles

# Matches article URLs: /{YYYY}/{MM}/{DD}/{slug}/
_URL_DATE_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/([^/]+)/")


class JamaicaObserverArchiveDiscoverer:
    """
    Discovers articles from Jamaica Observer daily archive pages.

    Fetches https://www.jamaicaobserver.com/{YYYY}/{MM}/{DD}/ for each day in
    the date range, extracts article links, and follows pagination if present.

    This strategy covers the period not available in WordPress sitemaps
    (approximately Sep 2025 onward).

    URL Pattern:
        Archive page: https://www.jamaicaobserver.com/{YYYY}/{MM}/{DD}/
        Article URL:  https://www.jamaicaobserver.com/{YYYY}/{MM}/{DD}/{slug}/
        Paginated:    https://www.jamaicaobserver.com/{YYYY}/{MM}/{DD}/page/{N}/

    Discovery Strategy:
        1. Generate list of dates in [start_date, end_date]
        2. For each date: fetch archive page, extract article links by URL regex
        3. Probe pages sequentially (page/2/, page/3/, ...) until 404 or empty
        4. Skip 404 days (weekends/holidays) — not an error
        5. Track failed dates (5xx, network errors) in failed_dates

    Implements the ArticleDiscoverer protocol.

    Example:
        discoverer = JamaicaObserverArchiveDiscoverer(
            start_date=datetime(2025, 9, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 2, 25, tzinfo=timezone.utc),
        )
        articles = await discoverer.discover(news_source_id=2)
    """

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        base_url: str = "https://www.jamaicaobserver.com",
        timeout: int = 30,
        max_retries: int = 3,
        base_backoff: float = 2.0,
        crawl_delay: float = 1.5,
    ):
        """
        Initialize the Jamaica Observer archive discoverer.

        Args:
            start_date: Start of date range (inclusive). Must be timezone-aware.
            end_date: End of date range (inclusive). Must be timezone-aware.
            base_url: Base URL for the Jamaica Observer site.
            timeout: HTTP request timeout in seconds.
            max_retries: Maximum retry attempts for failed requests.
            base_backoff: Base for exponential backoff (seconds).
            crawl_delay: Delay between requests (seconds).
        """
        if start_date.tzinfo is None:
            raise ValueError("start_date must be timezone-aware")
        if end_date.tzinfo is None:
            raise ValueError("end_date must be timezone-aware")
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")

        self.start_date = start_date
        self.end_date = end_date
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.crawl_delay = crawl_delay

        # Populated during discover() — dates that failed after all retries
        self.failed_dates: list[str] = []

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        logger.info(
            f"Initialized JamaicaObserverArchiveDiscoverer: "
            f"{start_date.date()} to {end_date.date()}, "
            f"crawl_delay={crawl_delay}s"
        )

    async def discover(self, news_source_id: int) -> list[DiscoveredArticle]:
        """
        Discover articles from Jamaica Observer daily archive pages.

        Implements the ArticleDiscoverer protocol.

        Args:
            news_source_id: Database ID of the news source (2 for Jamaica Observer).

        Returns:
            List of deduplicated DiscoveredArticle instances.

        Raises:
            ValueError: If news_source_id is invalid.
        """
        if news_source_id <= 0:
            raise ValueError(f"news_source_id must be positive, got: {news_source_id}")

        self.failed_dates = []

        dates = self._generate_dates()
        logger.info(
            f"Discovering archive pages for {len(dates)} dates: "
            f"{dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')}"
        )

        discovered_at = datetime.now(timezone.utc)
        all_articles: list[DiscoveredArticle] = []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=self.headers,
        ) as client:
            for i, date in enumerate(dates):
                if i > 0:
                    await asyncio.sleep(self.crawl_delay)

                date_str = date.strftime("%Y-%m-%d")
                try:
                    articles = await self._fetch_date_articles(
                        client, date, news_source_id, discovered_at
                    )
                    all_articles.extend(articles)
                    logger.info(f"Fetched {date_str} — {len(articles)} articles")
                except Exception as e:
                    logger.error(f"Failed to process {date_str}: {e}", exc_info=True)
                    self.failed_dates.append(date_str)

        unique_articles = deduplicate_discovered_articles(all_articles)
        logger.info(
            f"Discovery complete: {len(unique_articles)} unique articles, "
            f"{len(self.failed_dates)} failed dates"
        )
        return unique_articles

    async def _fetch_date_articles(
        self,
        client: httpx.AsyncClient,
        date: datetime,
        news_source_id: int,
        discovered_at: datetime,
    ) -> list[DiscoveredArticle]:
        """
        Fetch all articles for a single date, following pagination.

        Pagination links are JavaScript-rendered and not present in static HTML,
        so pages are probed sequentially until a 404 or empty page is returned.

        Args:
            client: HTTP client.
            date: The date to fetch.
            news_source_id: Database ID of the news source.
            discovered_at: Shared timestamp for all discovered articles.

        Returns:
            List of DiscoveredArticle instances for this date.
        """
        articles: list[DiscoveredArticle] = []

        for page_num in range(1, 1000):
            url = self._build_archive_url(date, page_num)

            if page_num > 1:
                await asyncio.sleep(self.crawl_delay)

            html = await self._fetch_with_retry(client, url)
            if html is None:
                # 404 — no more pages (or no articles published this day)
                break

            page_articles = self._extract_articles(
                html, date, news_source_id, discovered_at
            )
            articles.extend(page_articles)

            if not page_articles:
                # Page returned 200 but no matching articles — past the last page
                break

        return articles

    def _build_archive_url(self, date: datetime, page: int = 1) -> str:
        """Build the daily archive page URL for a given date and page number."""
        base = f"{self.base_url}/{date.strftime('%Y/%m/%d')}/"
        if page > 1:
            return f"{base}page/{page}/"
        return base

    def _extract_articles(
        self,
        html: str,
        date: datetime,
        news_source_id: int,
        discovered_at: datetime,
    ) -> list[DiscoveredArticle]:
        """
        Extract news articles from a daily archive page.

        Finds all <article class="... category_main ..."> elements, reads the
        URL from the ta_permalink attribute, and applies two filters:

        1. Date filter: ta_permalink URL must match the target date.
        2. Category filter: article must include "news" (exact, lowercase) in
           the comma-separated <div class="categories"> text.

        This approach correctly excludes:
        - Carousel / featured articles (class="cat_top_news")
        - Sidebar "today's articles" widgets (no category_main class)
        - Sports, Entertainment, International News, Regional, etc.

        Args:
            html: HTML content of the archive page.
            date: The date being crawled (for date-match filter).
            news_source_id: Database ID of the news source.
            discovered_at: Timestamp for all articles in this batch.

        Returns:
            List of DiscoveredArticle instances.
        """
        soup = BeautifulSoup(html, "html.parser")
        articles: list[DiscoveredArticle] = []
        seen_urls: set[str] = set()

        year, month, day = date.year, date.month, date.day
        published_date = datetime(year, month, day, tzinfo=timezone.utc)

        for article_el in soup.find_all("article", class_="category_main"):
            url = article_el.get("ta_permalink", "").strip()
            if not url:
                continue

            # Date filter: URL must contain the target date
            match = _URL_DATE_RE.search(url)
            if not match:
                continue

            link_year = int(match.group(1))
            link_month = int(match.group(2))
            link_day = int(match.group(3))
            slug = match.group(4)

            if (link_year, link_month, link_day) != (year, month, day):
                continue

            # Category filter: must include exact "news" category
            cats_div = article_el.find("div", class_="categories")
            if not cats_div:
                continue

            categories = {
                c.strip().lower()
                for c in cats_div.get_text(strip=True).split(",")
            }
            if "news" not in categories:
                continue

            # Normalise: ensure trailing slash
            if not url.endswith("/"):
                url = url + "/"

            if url in seen_urls:
                continue
            seen_urls.add(url)

            articles.append(
                DiscoveredArticle(
                    url=url,
                    news_source_id=news_source_id,
                    section="archive",
                    discovered_at=discovered_at,
                    title=slug,
                    published_date=published_date,
                )
            )

        return articles

    async def _fetch_with_retry(self, client: httpx.AsyncClient, url: str) -> str | None:
        """
        Fetch a URL with exponential backoff retry logic.

        Args:
            client: HTTP client.
            url: URL to fetch.

        Returns:
            Response text, or None if the server returned 404.

        Raises:
            httpx.HTTPStatusError: If all retry attempts fail with a non-404 HTTP error.
            httpx.RequestError: If all retry attempts fail with a network error.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.get(url)

                if response.status_code == 404:
                    logger.debug(f"404 for {url} — no articles this day")
                    return None

                response.raise_for_status()
                return response.text

            except httpx.HTTPStatusError as e:
                if attempt == self.max_retries:
                    logger.error(
                        f"Failed to fetch {url} after {self.max_retries} attempts: {e}"
                    )
                    raise

                backoff = self.base_backoff**attempt
                logger.warning(
                    f"Attempt {attempt}/{self.max_retries} failed for {url}, "
                    f"retrying in {backoff}s: {e}"
                )
                await asyncio.sleep(backoff)

            except httpx.RequestError as e:
                if attempt == self.max_retries:
                    logger.error(
                        f"Failed to fetch {url} after {self.max_retries} attempts: {e}"
                    )
                    raise

                backoff = self.base_backoff**attempt
                logger.warning(
                    f"Attempt {attempt}/{self.max_retries} failed for {url}, "
                    f"retrying in {backoff}s: {e}"
                )
                await asyncio.sleep(backoff)

        raise RuntimeError(f"Failed to fetch {url} after {self.max_retries} attempts")

    def _generate_dates(self) -> list[datetime]:
        """
        Generate list of dates from start_date to end_date (inclusive).

        Returns:
            List of timezone-aware datetimes at midnight UTC.
        """
        dates: list[datetime] = []
        current = datetime(
            self.start_date.year,
            self.start_date.month,
            self.start_date.day,
            tzinfo=timezone.utc,
        )
        end = datetime(
            self.end_date.year,
            self.end_date.month,
            self.end_date.day,
            tzinfo=timezone.utc,
        )

        while current <= end:
            dates.append(current)
            current += timedelta(days=1)

        return dates
