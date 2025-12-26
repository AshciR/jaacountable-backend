"""Base protocol for article persistence services."""
from typing import Protocol
import asyncpg
from src.article_extractor.models import ExtractedArticleContent
from src.article_classification.models import ClassificationResult, NormalizedEntity
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

    Note on transaction management:
    - Caller manages connection lifecycle (gets from db_config.connection())
    - Service manages transaction boundaries (creates from connection)
    - This separation allows for clean, testable code
    """

    async def store_article_with_classifications(
        self,
        conn: asyncpg.Connection,
        extracted: ExtractedArticleContent,
        url: str,
        section: str,
        relevant_classifications: list[ClassificationResult],
        normalized_entities: list[NormalizedEntity],
        news_source_id: int = 1,
    ) -> ArticleStorageResult:
        """
        Store an article with its classifications in a single transaction.

        The caller must provide a database connection, but this method manages
        the transaction to ensure article and classifications are stored atomically.

        Args:
            conn: Database connection (caller manages lifecycle)
            extracted: Extracted article content from ArticleExtractionService
            url: Original article URL
            section: Article section (e.g., "news", "lead-stories")
            relevant_classifications: List of relevant classification results
            normalized_entities: List of normalized entities with original/normalized pairs
            news_source_id: Database ID of news source (default: 1 for Jamaica Gleaner)

        Returns:
            ArticleStorageResult with storage outcome and metadata

        Raises:
            Exception: If storage fails (not including duplicates)
        """
        ...
