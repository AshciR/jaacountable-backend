"""Base protocol for article persistence services."""
from typing import Protocol
from config.database import DatabaseConfig
from src.article_extractor.models import ExtractedArticleContent
from src.article_classification.models import ClassificationResult
from .models.domain import ArticleStorageResult


class ArticlePersistenceService(Protocol):
    """
    Protocol for article persistence services using structural subtyping.

    This Protocol defines the interface for article persistence without
    requiring inheritance. Any class that implements the
    store_article_with_classifications() method with the correct signature
    can be used as an ArticlePersistenceService.

    This enables dependency injection and testability:
    - No need to inherit from a base class
    - Duck typing with type safety
    - Easy to mock in tests
    """

    async def store_article_with_classifications(
        self,
        db_config: DatabaseConfig,
        extracted: ExtractedArticleContent,
        url: str,
        section: str,
        relevant_classifications: list[ClassificationResult],
        news_source_id: int = 1,
    ) -> ArticleStorageResult:
        """
        Store an article with its classifications in a single transaction.

        Args:
            db_config: Database configuration for connection pool
            extracted: Extracted article content from ArticleExtractionService
            url: Original article URL
            section: Article section (e.g., "news", "lead-stories")
            relevant_classifications: List of relevant classification results
            news_source_id: Database ID of news source (default: 1 for Jamaica Gleaner)

        Returns:
            ArticleStorageResult with storage outcome and metadata

        Raises:
            Exception: If storage fails (not including duplicates)
        """
        ...
