"""Base protocol for article orchestration strategies."""
from typing import Protocol
import asyncpg

from .models import OrchestrationResult


class ArticleOrchestrator(Protocol):
    """
    Protocol for article orchestration strategies using structural subtyping.

    This Protocol defines the interface for article orchestrators without
    requiring inheritance. Any class that implements the process_article() method
    with the correct signature can be used as an ArticleOrchestrator.

    This enables the Strategy Pattern with maximum flexibility:
    - No need to inherit from a base class
    - Duck typing with type safety
    - Easy to add new orchestration strategies

    Example:
        class MyOrchestrator:  # No inheritance needed!
            async def process_article(
                self,
                conn: asyncpg.Connection,
                url: str,
                section: str,
                news_source_id: int = 1,
                min_confidence: float = 0.7,
            ) -> OrchestrationResult:
                # Implementation here
                pass

        # MyOrchestrator satisfies ArticleOrchestrator Protocol
    """

    async def process_article(
        self,
        conn: asyncpg.Connection,
        url: str,
        section: str,
        news_source_id: int = 1,
        min_confidence: float = 0.7,
    ) -> OrchestrationResult:
        """
        Process an article through the full pipeline: Extract → Classify → Store.

        Args:
            conn: Database connection (caller manages lifecycle)
            url: Article URL to process
            section: Article section/category (e.g., "news", "lead-stories")
            news_source_id: Database ID of news source (default: 1 for Jamaica Gleaner)
            min_confidence: Minimum confidence threshold for relevance (default: 0.7)

        Returns:
            OrchestrationResult with processing outcome and metadata

        Example:
            orchestrator = PipelineOrchestrationService()
            async with db_config.connection() as conn:
                result = await orchestrator.process_article(
                    conn=conn,
                    url="https://jamaica-gleaner.com/article/news/...",
                    section="news",
                )
                if result.stored:
                    print(f"Article stored with ID: {result.article_id}")
        """
        ...
