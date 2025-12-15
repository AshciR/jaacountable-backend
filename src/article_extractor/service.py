"""Article extraction service with strategy pattern."""
import requests
from urllib.parse import urlparse

from .models import ExtractedArticleContent
from src.article_extractor.extractors.gleaner_extractor import GleanerExtractor


class ArticleExtractionService:
    """
    Main service for extracting article content using domain-specific strategies.

    This service implements the Context in the Strategy Pattern:
    1. Fetches HTML from the URL
    2. Determines which extractor strategy to use based on domain
    3. Delegates extraction to the appropriate strategy
    4. Returns structured ArticleContent

    Supported domains (Phase 1):
    - jamaica-gleaner.com (via GleanerExtractor - updated December 2025)

    Example:
        service = ArticleExtractionService()
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
            # Phase 2: Add Radio Jamaica extractor
            # 'radiojamaicanewsonline.com': RadioJamaicaExtractor(),
        }

    def extract_article_content(self, url: str) -> ExtractedArticleContent:
        """
        Extract structured article content from URL.

        Args:
            url: Full article URL

        Returns:
            ArticleContent with extracted title, full_text, author, published_date

        Raises:
            ValueError: If URL is invalid or domain is not supported
            requests.HTTPError: If HTTP request fails
            requests.RequestException: For other network errors
        """
        # Parse and validate URL, extract domain
        domain = _parse_and_validate_url(url)

        # Select extraction strategy based on domain
        extractor = self.extractors.get(domain)
        if not extractor:
            supported = ", ".join(self.extractors.keys())
            raise ValueError(
                f"Unsupported domain: {domain}. " f"Supported domains: {supported}"
            )

        # Fetch HTML content
        html = _fetch_html(url)

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


def _fetch_html(url: str) -> str:
    """
    Fetch HTML content from URL.

    Args:
        url: Article URL

    Returns:
        Raw HTML content

    Raises:
        requests.HTTPError: If HTTP request fails (4xx, 5xx)
        requests.RequestException: For other network errors
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # Synchronous request (matches existing tools.py pattern)
    response = requests.get(url, headers=headers, timeout=30)

    # Raise exception for HTTP errors (4xx, 5xx)
    # This will propagate to caller for handling
    response.raise_for_status()

    return response.text
