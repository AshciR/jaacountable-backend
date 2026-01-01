"""Base protocol for article extraction strategies."""
from typing import Protocol
from .models import ExtractedArticleContent


class ArticleExtractor(Protocol):
    """
    Protocol for article extraction strategies using structural subtyping.

    This Protocol defines the interface for article extractors without
    requiring inheritance. Any class that implements the extract() method
    with the correct signature can be used as an ArticleExtractor.

    This enables the Strategy Pattern with maximum flexibility:
    - No need to inherit from a base class
    - Duck typing with type safety
    - Easy to add new extractors

    Example:
        class MyExtractor:  # No inheritance needed!
            def extract(self, html: str, url: str) -> ArticleContent:
                # Implementation here
                pass

        # MyExtractor satisfies ArticleExtractor Protocol
    """

    def extract(self, html: str, url: str) -> ExtractedArticleContent:
        """
        Extract structured article content from HTML.

        Args:
            html: Raw HTML content of the article page
            url: Article URL (for context/debugging)

        Returns:
            ArticleContent with extracted title, full_text, author, and published_date

        Raises:
            ValueError: If required elements are missing or parsing fails
        """
        ...


class ArticleExtractionService(Protocol):
    """
    Protocol for article extraction services.

    This protocol defines the interface for services that extract article
    content from URLs using domain-specific strategies. Any class that
    implements the extract_article_content() method with the correct
    signature can be used as an ArticleExtractionService.

    This enables:
    - Dependency injection with type safety
    - Easy mocking in tests
    - Multiple service implementations (e.g., caching, rate-limiting)

    Example:
        class MyExtractionService:  # No inheritance needed!
            async def extract_article_content(self, url: str) -> ExtractedArticleContent:
                # Implementation here
                pass

        # MyExtractionService satisfies ArticleExtractionService Protocol
    """

    async def extract_article_content(self, url: str) -> ExtractedArticleContent:
        """
        Extract structured article content from URL.

        Args:
            url: Full article URL

        Returns:
            ExtractedArticleContent with title, full_text, author, published_date

        Raises:
            ValueError: If URL is invalid or domain is not supported
            httpx.HTTPStatusError: If HTTP request fails
            httpx.HTTPError: For other network errors
        """
        ...
