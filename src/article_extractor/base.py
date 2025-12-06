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
