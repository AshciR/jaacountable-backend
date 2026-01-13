"""Article extraction service with strategy pattern."""
import asyncio
from urllib.parse import urlparse

import httpx
from loguru import logger

from src.article_extractor.extractors.gleaner_extractor import GleanerExtractor
from src.article_extractor.extractors.gleaner_archive_extractor import GleanerArchiveExtractor
from .base import ArticleExtractor
from .models import ExtractedArticleContent


class DefaultArticleExtractionService:
    """
    Default implementation of ArticleExtractionService protocol.

    This service implements the Context in the Strategy Pattern:
    1. Fetches HTML from the URL
    2. Determines which extractor strategy to use based on domain
    3. Delegates extraction to the appropriate strategy
    4. Returns structured ArticleContent

    Supported domains (Phase 1):
    - jamaica-gleaner.com (via GleanerExtractor - updated December 2025)
    - gleaner.newspaperarchive.com (via GleanerArchiveExtractor - historical archives)

    Example:
        service = DefaultArticleExtractionService()
        content = service.extract_article_content(
            "https://jamaica-gleaner.com/article/news/..."
        )
        print(content.title)
        print(content.full_text)

    Adding new sources:
        1. Create new extractor class implementing ArticleExtractor Protocol
        2. Add domain mapping to self.extractors dict
        3. No changes to existing code needed!
    """

    def __init__(self):
        """Initialize service with domain-to-extractor mappings."""
        # Map domains to extraction strategies
        # Note: Domain keys should NOT include 'www.' prefix
        self.extractors = {
            "jamaica-gleaner.com": GleanerExtractor(),
            "gleaner.newspaperarchive.com": GleanerArchiveExtractor(),
            # Phase 2: Add Radio Jamaica extractor
            # 'radiojamaicanewsonline.com': RadioJamaicaExtractor(),
        }

    async def __aenter__(self):
        """
        Initialize HTTP client for connection pooling.

        Enables using the service as an async context manager for improved performance
        when processing multiple articles. The client will be reused across all
        extract_article_content() calls within the context.

        Example:
            async with DefaultArticleExtractionService() as service:
                content1 = await service.extract_article_content(url1)
                content2 = await service.extract_article_content(url2)
                # Same client instance reused for both extractions

        Returns:
            Self to enable async context manager pattern
        """
        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Clean up HTTP client and close connections.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        if hasattr(self, "_http_client") and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def extract_article_content(self, url: str) -> ExtractedArticleContent:
        """
        Extract structured article content from URL.

        Args:
            url: Full article URL

        Returns:
            ArticleContent with extracted title, full_text, author, published_date

        Raises:
            ValueError: If URL is invalid or domain is not supported
            httpx.HTTPStatusError: If HTTP request fails
            httpx.HTTPError: For other network errors
        """
        # Parse and validate URL, extract domain
        domain = _parse_and_validate_url(url)

        # Select extraction strategy based on domain
        extractor: ArticleExtractor | None = self.extractors.get(domain)
        if not extractor:
            supported = ", ".join(self.extractors.keys())
            raise ValueError(
                f"Unsupported domain: {domain}. " f"Supported domains: {supported}"
            )

        # Fetch HTML content using pooled client if available
        if hasattr(self, "_http_client") and self._http_client is not None:
            # Use pooled client (context manager mode)
            html = await _fetch_html(url, self._http_client)
        else:
            # Backward compatibility: create temporary client
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            ) as temp_client:
                html = await _fetch_html(url, temp_client)

        # Execute extraction strategy
        # Note: Let extraction errors propagate (fail-fast approach)
        return extractor.extract(html, url)


def _parse_and_validate_url(url: str) -> str:
    """
    Parse and validate URL, extract normalized domain.

    Args:
        url: Article URL

    Returns:
        Normalized domain name (without www. prefix)

    Raises:
        ValueError: If URL is invalid or malformed
    """
    # Validate URL format
    if not url or not url.strip():
        raise ValueError("URL cannot be empty")

    url = url.strip()

    # Parse URL to extract domain
    try:
        parsed_url = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {url}") from e

    if not parsed_url.scheme or not parsed_url.netloc:
        raise ValueError(f"URL must include scheme and domain: {url}")

    # Normalize domain (remove www. prefix)
    domain = parsed_url.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    return domain


async def _fetch_html(
    url: str,
    client: httpx.AsyncClient,
    timeout: int = 30,
    max_retries: int = 3,
    base_backoff: float = 2.0,
) -> str:
    """
    Fetch HTML content from URL with exponential backoff retry logic.

    This function implements smart retry logic that only retries transient errors:
    - 5xx server errors (500, 502, 503, 504, etc.)
    - Network errors (timeouts, connection failures, DNS errors)

    Client errors (4xx) are NOT retried as they indicate permanent failures
    (e.g., 404 Not Found, 401 Unauthorized, 403 Forbidden).

    Args:
        url: Article URL
        client: httpx.AsyncClient instance for making requests
        timeout: HTTP request timeout in seconds (default: 30)
        max_retries: Maximum retry attempts for failed requests (default: 3)
        base_backoff: Base for exponential backoff calculation (default: 2.0)

    Returns:
        Raw HTML content

    Raises:
        httpx.HTTPStatusError: If HTTP request fails after all retries
        httpx.RequestError: If network error persists after all retries
    """
    for attempt in range(1, max_retries + 1):
        try:
            response = await client.get(url, timeout=timeout)

            # Raise exception for HTTP errors (4xx, 5xx)
            response.raise_for_status()

            # Success - return HTML content
            return response.text

        except httpx.HTTPStatusError as e:
            # Check if this is a retryable error (5xx server error)
            if e.response.status_code >= 500:
                # 5xx server error - transient, worth retrying
                if attempt == max_retries:
                    logger.error(
                        f"Failed to fetch {url} after {max_retries} retries: "
                        f"{e.response.status_code} {e.response.reason_phrase}"
                    )
                    raise

                # Calculate exponential backoff: 2^1=2s, 2^2=4s, 2^3=8s
                backoff_time = base_backoff**attempt
                logger.warning(
                    f"Attempt {attempt}/{max_retries} failed for {url} "
                    f"({e.response.status_code} {e.response.reason_phrase}), "
                    f"retrying in {backoff_time}s"
                )
                await asyncio.sleep(backoff_time)
            else:
                # 4xx client error - permanent failure, don't retry
                logger.error(
                    f"Client error fetching {url}: "
                    f"{e.response.status_code} {e.response.reason_phrase} "
                    f"(not retrying)"
                )
                raise

        except httpx.RequestError as e:
            # Network error (timeout, connection failure, DNS error, etc.)
            # These are transient and worth retrying
            if attempt == max_retries:
                logger.error(
                    f"Failed to fetch {url} after {max_retries} retries: {e}"
                )
                raise

            # Calculate exponential backoff
            backoff_time = base_backoff**attempt
            logger.warning(
                f"Attempt {attempt}/{max_retries} failed for {url}, "
                f"retrying in {backoff_time}s: {e}"
            )
            await asyncio.sleep(backoff_time)

    # This line should never be reached, but helps type checker
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} retries")
