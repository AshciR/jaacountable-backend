"""
Article persistence service layer.

Provides high-level operations for storing articles and classifications.
"""
import logging

from asyncpg import UniqueViolationError

from config.database import DatabaseConfig
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


async def store_article_with_classifications(
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
        ArticleStorageResult with:
            - stored: bool (True if stored, False if duplicate)
            - article_id: int | None (ID of stored article, None if duplicate)
            - classification_count: int (number of classifications stored)
            - article: Article | None (stored article model, None if duplicate)
            - classifications: list[Classification] (list of stored classifications)

    Raises:
        Exception: If storage fails (not including duplicates)

    Example:
        >>> result = await store_article_with_classifications(
        ...     db_config=db_config,
        ...     extracted=extracted_content,
        ...     url=url,
        ...     section="news",
        ...     relevant_classifications=relevant_results,
        ... )
        >>> print(f"Stored article ID: {result.article_id}")
    """
    article_repo = ArticleRepository()
    classification_repo = ClassificationRepository()

    async with db_config.connection() as conn:
        async with conn.transaction():
            # Convert to Article domain model
            article = extracted_content_to_article(
                extracted=extracted,
                url=url,
                section=section,
                news_source_id=news_source_id,
            )

            try:
                # Insert article (get article_id)
                stored_article = await article_repo.insert_article(conn, article)
                logger.info(f"Article stored with ID: {stored_article.id}")

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

            # Insert classifications
            stored_classifications = []
            for result in relevant_classifications:
                classification = classification_result_to_classification(
                    result=result,
                    article_id=stored_article.id,  # type: ignore
                )
                stored_classification = await classification_repo.insert_classification(
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
