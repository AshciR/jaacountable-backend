"""Article extraction service with strategy pattern."""
from urllib.parse import urlparse

import httpx

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

        # Fetch HTML content
        html = await _fetch_html(url)

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


async def _fetch_html(url: str) -> str:
    """
    Fetch HTML content from URL.

    Args:
        url: Article URL

    Returns:
        Raw HTML content

    Raises:
        httpx.HTTPStatusError: If HTTP request fails (4xx, 5xx)
        httpx.HTTPError: For other network errors
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # Async request with httpx.AsyncClient context manager
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, timeout=30)

        # Raise exception for HTTP errors (4xx, 5xx)
        # This will propagate to caller for handling
        response.raise_for_status()

        return response.text
