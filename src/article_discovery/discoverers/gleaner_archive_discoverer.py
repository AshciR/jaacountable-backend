"""Gleaner Archive article discoverer using date ranges and pagination."""

import asyncio
import re
from datetime import datetime, timedelta, timezone
from calendar import monthrange
from types import SimpleNamespace

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from src.article_discovery.models import DiscoveredArticle


class RedirectError(Exception):
    """Raised when a request is redirected to base page or unexpected location."""

    def __init__(self, message: str, redirect_url: str):
        super().__init__(message)
        self.response = SimpleNamespace(status_code=302, url=redirect_url)


class GleanerArchiveDiscoverer:
    """
    Discovers articles from Gleaner newspaper archive (gleaner.newspaperarchive.com).

    This discoverer finds historical archive pages by:
    1. Generating a date range (end_date going back days_back days)
    2. For each date, discovering all paginated pages by following <link rel="next"> tags
    3. Returning list[DiscoveredArticle] following the ArticleDiscoverer protocol

    URL Pattern:
        Base date URL: https://gleaner.newspaperarchive.com/kingston-gleaner/YYYY-MM-DD/
        Paginated URL: https://gleaner.newspaperarchive.com/kingston-gleaner/YYYY-MM-DD/page-N/

    Discovery Strategy:
        - Try base URL first (/YYYY-MM-DD/), fallback to /page-1/ if 404
        - Follow <link rel="next"> tags to discover all pages for each date
        - Apply crawl delay (default 2 seconds) between requests for respectful crawling
        - Fail-soft error handling: continue on date failures, retry on network errors

    Example:
        discoverer = GleanerArchiveDiscoverer(
            end_date=datetime(2025, 11, 23, tzinfo=timezone.utc),
            days_back=7
        )
        articles = await discoverer.discover(news_source_id=1)
    """

    def __init__(
        self,
        base_url: str = "https://gleaner.newspaperarchive.com",
        publication: str = "kingston-gleaner",
        end_date: datetime | None = None,
        days_back: int = 7,
        timeout: int = 30,
        max_retries: int = 3,
        base_backoff: float = 2.0,
        crawl_delay: float = 2.0,
    ):
        """
        Initialize Gleaner Archive Discoverer.

        Args:
            base_url: Base URL for archive (default: https://gleaner.newspaperarchive.com)
            publication: Publication name (default: kingston-gleaner)
            end_date: End date for discovery range (default: now)
            days_back: Number of days to go back from end_date (default: 7)
            timeout: HTTP request timeout in seconds (default: 30)
            max_retries: Maximum retry attempts for failed requests (default: 3)
            base_backoff: Base for exponential backoff calculation (default: 2.0)
            crawl_delay: Delay between requests in seconds (default: 2.0)
        """
        self.client = None
        self.base_url = base_url.rstrip("/")
        self.publication = publication
        self.end_date = end_date or datetime.now(timezone.utc)
        self.days_back = days_back
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.crawl_delay = crawl_delay

        # Headers for HTTP requests
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        logger.info(
            f"Initialized GleanerArchiveDiscoverer: {self.base_url}/{self.publication}, "
            f"end_date={self.end_date.date()}, days_back={self.days_back}"
        )

    @classmethod
    def for_month(
        cls,
        year: int,
        month: int,
        base_url: str = "https://gleaner.newspaperarchive.com",
        publication: str = "kingston-gleaner",
        timeout: int = 30,
        max_retries: int = 3,
        base_backoff: float = 2.0,
        crawl_delay: float = 2.0,
    ) -> "GleanerArchiveDiscoverer":
        """
        Create discoverer for a specific month and year.

        Factory method that converts (year, month) into date range covering
        the entire month (inclusive).

        Args:
            year: Year (e.g., 2021)
            month: Month (1-12)
            base_url: Base URL for archive (default: https://gleaner.newspaperarchive.com)
            publication: Publication name (default: kingston-gleaner)
            timeout: HTTP request timeout in seconds (default: 30)
            max_retries: Maximum retry attempts for failed requests (default: 3)
            base_backoff: Base for exponential backoff calculation (default: 2.0)
            crawl_delay: Delay between requests in seconds (default: 2.0)

        Returns:
            GleanerArchiveDiscoverer configured for the entire month

        Raises:
            ValueError: If year/month is invalid

        Example:
            # Discover all articles from November 2021
            discoverer = GleanerArchiveDiscoverer.for_month(
                year=2021,
                month=11
            )
            articles = await discoverer.discover(news_source_id=1)
        """
        # Validate year and month
        if year < 1900 or year > 3000:
            raise ValueError(f"Invalid year: {year} (must be between 1900-3000)")

        if month < 1 or month > 12:
            raise ValueError(f"Invalid month: {month} (must be between 1-12)")

        # Start date: First day of month at midnight UTC
        start_date = datetime(year, month, 1, tzinfo=timezone.utc)

        # End date: Last day of month at midnight UTC
        days_in_month = monthrange(year, month)[1]  # Returns (weekday, days)
        end_date = datetime(year, month, days_in_month, tzinfo=timezone.utc)

        # Calculate days_back from date range
        days_back = (end_date.date() - start_date.date()).days

        # Create instance using existing constructor
        return cls(
            base_url=base_url,
            publication=publication,
            end_date=end_date,
            days_back=days_back,
            timeout=timeout,
            max_retries=max_retries,
            base_backoff=base_backoff,
            crawl_delay=crawl_delay,
        )

    @classmethod
    def for_date(
        cls,
        year: int,
        month: int,
        day: int,
        base_url: str = "https://gleaner.newspaperarchive.com",
        publication: str = "kingston-gleaner",
        timeout: int = 30,
        max_retries: int = 3,
        base_backoff: float = 2.0,
        crawl_delay: float = 2.0,
    ) -> "GleanerArchiveDiscoverer":
        """
        Create discoverer for a specific date.

        Factory method for discovering articles from a single date.
        Useful for retrying individual dates that failed during bulk discovery.

        Args:
            year: Year (e.g., 2021)
            month: Month (1-12)
            day: Day (1-31)
            base_url: Base URL for archive (default: https://gleaner.newspaperarchive.com)
            publication: Publication name (default: kingston-gleaner)
            timeout: HTTP request timeout in seconds (default: 30)
            max_retries: Maximum retry attempts for failed requests (default: 3)
            base_backoff: Base for exponential backoff calculation (default: 2.0)
            crawl_delay: Delay between requests in seconds (default: 2.0)

        Returns:
            GleanerArchiveDiscoverer configured for the specific date

        Raises:
            ValueError: If date is invalid

        Example:
            # Discover all articles from November 15, 2021
            discoverer = GleanerArchiveDiscoverer.for_date(
                year=2021,
                month=11,
                day=15
            )
            articles = await discoverer.discover(news_source_id=1)
        """
        # Validate year
        if year < 1900 or year > 3000:
            raise ValueError(f"Invalid year: {year} (must be between 1900-3000)")

        # Validate month
        if month < 1 or month > 12:
            raise ValueError(f"Invalid month: {month} (must be between 1-12)")

        # Validate day (basic check)
        if day < 1 or day > 31:
            raise ValueError(f"Invalid day: {day} (must be between 1-31)")

        # Create date (this will raise ValueError if invalid, e.g., Feb 30)
        try:
            target_date = datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError as e:
            raise ValueError(f"Invalid date: {year}-{month:02d}-{day:02d} - {e}")

        # Create instance for single date (days_back=0 means just this one date)
        return cls(
            base_url=base_url,
            publication=publication,
            end_date=target_date,
            days_back=0,
            timeout=timeout,
            max_retries=max_retries,
            base_backoff=base_backoff,
            crawl_delay=crawl_delay,
        )

    async def discover(self, news_source_id: int) -> list[DiscoveredArticle]:
        """
        Discover archive articles for the configured date range.

        Implements the ArticleDiscoverer protocol.

        Args:
            news_source_id: Database ID of the news source (e.g., 1 for Jamaica Gleaner)

        Returns:
            List of DiscoveredArticle instances

        Raises:
            ValueError: If news_source_id is invalid
        """
        # Validate input
        if news_source_id <= 0:
            raise ValueError(f"news_source_id must be positive, got: {news_source_id}")

        logger.info(
            f"Starting archive discovery for news_source_id={news_source_id}, "
            f"date range: {self.end_date.date()} going back {self.days_back} days"
        )

        # Generate date range
        dates = self._generate_date_range()
        logger.info(f"Generated {len(dates)} dates to discover: {dates[0].date()} to {dates[-1].date()}")

        # Create async HTTP client and discover pages
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=self.headers
        ) as client:
            self.client = client

            # Discover pages for all dates (fail-soft: continue on date failures)
            all_articles: list[DiscoveredArticle] = []
            for date in dates:
                try:
                    articles = await self._discover_pages_for_date(client, date, news_source_id)
                    all_articles.extend(articles)
                    logger.info(f"Discovered {len(articles)} articles for {date.date()}")
                except Exception as e:
                    logger.exception(f"Failed to discover pages for {date.date()}: {e}")
                    # Continue with next date (fail-soft)
                    continue

        # Deduplicate by URL
        deduplicated = self._deduplicate_articles(all_articles)

        logger.info(
            f"Archive discovery complete: {len(deduplicated)} unique articles discovered "
            f"from {len(dates)} dates between {dates[0].date()} to {dates[-1].date()}"
        )

        return deduplicated

    def _generate_date_range(self) -> list[datetime]:
        """
        Generate list of dates from (end_date - days_back) to end_date.

        Returns:
            List of timezone-aware datetime objects at midnight UTC
        """
        end = self.end_date
        start = end - timedelta(days=self.days_back)

        dates: list[datetime] = []

        # Calculate number of days in range (inclusive)
        num_days = (end.date() - start.date()).days + 1

        for i in range(num_days):
            current_date = start.date() + timedelta(days=i)
            # Convert to timezone-aware datetime at midnight UTC
            date_at_midnight = datetime.combine(current_date, datetime.min.time()).replace(
                tzinfo=timezone.utc
            )
            dates.append(date_at_midnight)

        return dates

    async def _discover_pages_for_date(
        self, client: httpx.AsyncClient, date: datetime, news_source_id: int
    ) -> list[DiscoveredArticle]:
        """
        Discover all paginated pages for a single date.

        Strategy:
        1. Try base URL first (/YYYY-MM-DD/)
        2. If 404, fallback to /page-1/
        3. Parse page and create DiscoveredArticle
        4. Follow <link rel="next"> tags until exhausted
        5. Apply crawl delay between requests

        Args:
            client: HTTP client to use for requests
            date: Date to discover pages for
            news_source_id: Database ID of the news source

        Returns:
            List of DiscoveredArticle for this date

        Raises:
            httpx.RequestError: If all retry attempts fail
        """
        articles: list[DiscoveredArticle] = []

        # Try base URL first
        base_url = self._construct_date_url(date)
        logger.debug(f"Trying base URL: {base_url}")

        try:
            html = await self._fetch_page_with_retry(client, base_url)
            current_url = base_url
        except RedirectError as e:
            # Redirected to base page - date doesn't exist, skip without fallback
            logger.info(f"Date {date.date()} does not exist in archive (redirected), skipping.")
            return []  # Return empty list, no articles for this date
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Real 404 - try fallback to page-1 URL
                page_1_url = self._construct_date_url(date, page=1)
                logger.debug(f"Base URL returned 404, trying page-1: {page_1_url}")
                html = await self._fetch_page_with_retry(client, page_1_url)
                current_url = page_1_url
            else:
                raise

        # Process first page
        article = self._construct_discovered_article(current_url, html, news_source_id)
        articles.append(article)
        logger.debug(f"Discovered page: {current_url}")

        # Follow pagination links
        page_count = 1
        while True:
            # Extract next page URL
            next_url = self._parse_next_page_url(html)

            if not next_url:
                # No more pages - normal termination
                logger.debug(f"No more pages for {date.date()} (total: {page_count} pages)")
                break

            # Apply crawl delay before next request
            logger.debug(f"Applying crawl delay: {self.crawl_delay}s")
            await asyncio.sleep(self.crawl_delay)

            # Fetch next page
            logger.debug(f"Following next link: {next_url}")
            html = await self._fetch_page_with_retry(client, next_url)

            # Process next page
            article = self._construct_discovered_article(next_url, html, news_source_id)
            articles.append(article)
            page_count += 1

            current_url = next_url

        return articles

    def _check_for_redirect(self, response: httpx.Response, requested_url: str) -> None:
        """
        Check if response was redirected and raise appropriate RedirectError.

        Args:
            response: The HTTP response object
            requested_url: The original URL that was requested

        Raises:
            RedirectError: With status 302 if redirected to base page (date doesn't exist)
                          or redirected to unexpected location
        """
        # Check if we were redirected
        if not (hasattr(response, 'history') and isinstance(response.history, list) and len(response.history) > 0):
            return  # No redirect, nothing to do

        expected_base_page = f"{self.base_url}/{self.publication}/"

        if str(response.url) == expected_base_page or str(response.url) == expected_base_page.rstrip('/'):
            # Redirected to base page - this date doesn't exist in archive
            message = (
                f"Redirected to base page: {requested_url} -> {response.url}. "
                f"Date does not exist in archive."
            )
            logger.info(message)
        else:
            # Redirected to unexpected page
            message = f"Redirected to unexpected page: {requested_url} -> {response.url}"
            logger.warning(message)

        raise RedirectError(message, str(response.url))

    def _construct_date_url(self, date: datetime, page: int | None = None) -> str:
        """
        Construct archive URL for a given date and optional page number.

        Args:
            date: Date for the URL
            page: Optional page number (None for base URL, int for /page-N/)

        Returns:
            Full archive URL

        Examples:
            _construct_date_url(date) -> "https://gleaner.newspaperarchive.com/kingston-gleaner/2025-11-23/"
            _construct_date_url(date, 5) -> "https://gleaner.newspaperarchive.com/kingston-gleaner/2025-11-23/page-5/"
        """
        date_str = date.strftime("%Y-%m-%d")

        if page is None:
            return f"{self.base_url}/{self.publication}/{date_str}/"
        else:
            return f"{self.base_url}/{self.publication}/{date_str}/page-{page}/"

    async def _fetch_page_with_retry(self, client: httpx.AsyncClient, url: str) -> str:
        """
        Fetch HTML page with exponential backoff retry logic.

        Args:
            client: HTTP client to use for requests
            url: URL to fetch

        Returns:
            HTML content as string

        Raises:
            httpx.RequestError: If all retry attempts fail
            RedirectError: If URL redirects (404 equivalent)
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.get(url)

                # Check for redirects (raises RedirectError with 302 if redirected)
                self._check_for_redirect(response, url)

                # Check for other HTTP errors
                response.raise_for_status()
                return response.text

            except RedirectError:
                # Redirect detected - don't retry, let caller handle it
                raise  # Immediately propagate redirect errors without retrying

            except httpx.HTTPStatusError as e:
                # For HTTP errors, apply retry logic
                if attempt == self.max_retries:
                    logger.error(
                        f"Failed to fetch {url} after {self.max_retries} retries: {e}"
                    )
                    raise

                # Calculate exponential backoff: 2^1=2s, 2^2=4s, 2^3=8s
                backoff_time = self.base_backoff**attempt
                logger.warning(
                    f"Attempt {attempt}/{self.max_retries} failed for {url}, "
                    f"retrying in {backoff_time}s: {e}"
                )
                await asyncio.sleep(backoff_time)

            except httpx.RequestError as e:
                # For network errors and other exceptions, apply retry logic
                if attempt == self.max_retries:
                    logger.error(
                        f"Failed to fetch {url} after {self.max_retries} retries: {e}"
                    )
                    raise

                # Calculate exponential backoff
                backoff_time = self.base_backoff**attempt
                logger.warning(
                    f"Attempt {attempt}/{self.max_retries} failed for {url}, "
                    f"retrying in {backoff_time}s: {e}"
                )
                await asyncio.sleep(backoff_time)

        # This line should never be reached, but helps type checker
        raise RuntimeError(f"Failed to fetch {url} after {self.max_retries} retries")

    def _parse_next_page_url(self, html: str) -> str | None:
        """
        Extract next page URL from <link rel="next"> tag in HTML.

        Args:
            html: HTML content to parse

        Returns:
            Next page URL if found, None otherwise

        Example HTML:
            <link rel="next" href="https://gleaner.newspaperarchive.com/kingston-gleaner/2021-11-07/page-6/" />
        """
        soup = BeautifulSoup(html, "html.parser")
        next_link = soup.find("link", {"rel": "next"})

        if next_link and next_link.get("href"):
            next_url = next_link["href"]
            logger.debug(f"Found next link: {next_url}")
            return str(next_url)

        return None

    def _extract_page_title(self, html: str) -> str | None:
        """
        Extract simple page title from HTML metadata.

        Tries multiple sources in order:
        1. <meta property="og:title">
        2. <title> tag

        Args:
            html: HTML content to parse

        Returns:
            Page title if found, None otherwise
        """
        soup = BeautifulSoup(html, "html.parser")

        # Try Open Graph title first (more specific)
        og_title = soup.find("meta", {"property": "og:title"})
        if og_title and og_title.get("content"):
            title = og_title["content"]
            if isinstance(title, str) and title.strip():
                return title.strip()

        # Fallback to title tag
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            if title:
                return title

        return None

    def _parse_date_from_url(self, url: str) -> datetime | None:
        """
        Parse published date from archive URL.

        URL pattern: .../kingston-gleaner/YYYY-MM-DD/...

        Args:
            url: Archive URL

        Returns:
            Timezone-aware datetime at midnight UTC, or None if parsing fails

        Example:
            "https://gleaner.newspaperarchive.com/kingston-gleaner/2025-11-23/page-5/"
            -> datetime(2025, 11, 23, 0, 0, 0, tzinfo=timezone.utc)
        """
        # Extract date pattern YYYY-MM-DD from URL
        match = re.search(r"/(\d{4}-\d{2}-\d{2})/", url)

        if not match:
            logger.warning(f"Could not parse date from URL: {url}")
            return None

        date_str = match.group(1)

        try:
            # Parse date and make timezone-aware at midnight UTC
            published_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            return published_date
        except ValueError as e:
            logger.warning(f"Invalid date format in URL {url}: {e}")
            return None

    def _construct_discovered_article(
        self, url: str, html: str, news_source_id: int
    ) -> DiscoveredArticle:
        """
        Construct DiscoveredArticle from page URL and HTML.

        Extracts:
        - title: From page metadata (og:title or <title>)
        - published_date: From URL date component

        Args:
            url: Full archive page URL
            html: HTML content
            news_source_id: Database ID of the news source

        Returns:
            DiscoveredArticle instance
        """
        # Extract metadata
        title = self._extract_page_title(html)
        published_date = self._parse_date_from_url(url)

        return DiscoveredArticle(
            url=url,
            news_source_id=news_source_id,
            section="archive",
            discovered_at=datetime.now(timezone.utc),
            title=title,
            published_date=published_date,
        )

    def _deduplicate_articles(
        self, articles: list[DiscoveredArticle]
    ) -> list[DiscoveredArticle]:
        """
        Remove duplicate articles by URL.

        Keeps first occurrence of each unique URL.

        Args:
            articles: List of articles (may contain duplicates)

        Returns:
            List of articles with duplicates removed
        """
        seen_urls: set[str] = set()
        deduplicated: list[DiscoveredArticle] = []

        for article in articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                deduplicated.append(article)
            else:
                logger.debug(f"Duplicate URL found, skipping: {article.url}")

        if len(articles) != len(deduplicated):
            logger.info(
                f"Deduplicated {len(articles)} → {len(deduplicated)} articles "
                f"({len(articles) - len(deduplicated)} duplicates removed)"
            )

        return deduplicated
