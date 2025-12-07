"""
Article persistence service layer.

Provides high-level operations for storing articles and classifications.
"""
import logging
import asyncpg

from asyncpg import UniqueViolationError

from src.article_extractor.models import ExtractedArticleContent
from src.article_classification.models import ClassificationResult
from src.orchestration.converters import (
    extracted_content_to_article,
    classification_result_to_classification,
)
from .models.domain import ArticleStorageResult
from .repositories.article_repository import ArticleRepository
from .repositories.classification_repository import ClassificationRepository


logger = logging.getLogger(__name__)


class PostgresArticlePersistenceService:
    """
    PostgreSQL implementation of ArticlePersistenceService Protocol.

    Stores articles and classifications in PostgreSQL database
    with transactional guarantees. The service manages transaction
    boundaries while the caller manages connection lifecycle.
    """

    def __init__(
        self,
        article_repo: ArticleRepository | None = None,
        classification_repo: ClassificationRepository | None = None,
    ):
        """
        Initialize service with repository dependencies.

        Args:
            article_repo: Article repository (default: creates new instance)
            classification_repo: Classification repository (default: creates new instance)
        """
        self.article_repo = article_repo or ArticleRepository()
        self.classification_repo = classification_repo or ClassificationRepository()

    async def store_article_with_classifications(
        self,
        conn: asyncpg.Connection,
        extracted: ExtractedArticleContent,
        url: str,
        section: str,
        relevant_classifications: list[ClassificationResult],
        news_source_id: int = 1,
    ) -> ArticleStorageResult:
        """
        Store an article with its classifications in a single transaction.

        The caller must provide a connection, but this method manages the
        transaction to ensure article and classifications are stored atomically.

        Args:
            conn: Database connection (caller manages lifecycle)
            extracted: Extracted article content from ArticleExtractionService
            url: Original article URL
            section: Article section (e.g., "news", "lead-stories")
            relevant_classifications: List of relevant classification results
            news_source_id: Database ID of news source (default: 1 for Jamaica Gleaner)

        Returns:
            ArticleStorageResult with storage outcome and metadata

        Raises:
            UniqueViolationError: If article URL already exists (caught internally)
            Exception: For other database errors

        Example:
            >>> service = PostgresArticlePersistenceService()
            >>> async with db_config.connection() as conn:
            ...     result = await service.store_article_with_classifications(
            ...         conn=conn,
            ...         extracted=extracted_content,
            ...         url=url,
            ...         section="news",
            ...         relevant_classifications=results,
            ...     )
        """
        # Convert to Article domain model
        article = extracted_content_to_article(
            extracted=extracted,
            url=url,
            section=section,
            news_source_id=news_source_id,
        )

        try:
            async with conn.transaction():
                # Insert article (get article_id)
                stored_article = await self.article_repo.insert_article(conn, article)
                logger.info(f"Article stored with ID: {stored_article.id}")

                # Insert classifications
                stored_classifications = []
                for result in relevant_classifications:
                    classification = classification_result_to_classification(
                        result=result,
                        article_id=stored_article.id,  # type: ignore
                    )
                    stored_classification = await self.classification_repo.insert_classification(
                        conn, classification
                    )
                    stored_classifications.append(stored_classification)
                    logger.info(
                        f"Classification stored (type: {result.classifier_type.value}, "
                        f"confidence: {result.confidence:.2f})"
                    )

                return ArticleStorageResult(
                    stored=True,
                    article_id=stored_article.id,
                    classification_count=len(stored_classifications),
                    article=stored_article,
                    classifications=stored_classifications,
                )

        except UniqueViolationError:
            # Article already exists (URL unique constraint)
            logger.info(f"Article already exists, skipping: {url}")
            return ArticleStorageResult(
                stored=False,
                article_id=None,
                classification_count=0,
                article=None,
                classifications=[],
            )
