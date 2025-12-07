"""Model conversion utilities for persistence layer."""
from datetime import datetime, timezone

from src.article_extractor.models import ExtractedArticleContent
from src.article_classification.models import ClassificationResult
from .models.domain import Article, Classification


def extracted_content_to_article(
    extracted: ExtractedArticleContent,
    url: str,
    section: str,
    news_source_id: int
) -> Article:
    """
    Convert ExtractedArticleContent to Article domain model.

    Adds required database fields (news_source_id, fetched_at).

    Args:
        extracted: Content from ArticleExtractionService
        url: Original article URL
        section: Article section/category
        news_source_id: Database ID of news source (Jamaica Gleaner = 1)

    Returns:
        Article domain model ready for ArticleRepository

    Example:
        >>> article = extracted_content_to_article(
        ...     extracted=extracted,
        ...     url=url,
        ...     section="news",
        ...     news_source_id=1
        ... )
    """
    return Article(
        url=url,
        title=extracted.title,
        section=section,
        published_date=extracted.published_date,
        fetched_at=datetime.now(timezone.utc),
        full_text=extracted.full_text,
        news_source_id=news_source_id,
    )


def classification_result_to_classification(
    result: ClassificationResult,
    article_id: int
) -> Classification:
    """
    Convert ClassificationResult to Classification domain model.

    IMPORTANT: Can only be called AFTER article is stored (need article_id).

    Args:
        result: Result from ClassificationService
        article_id: Database ID of stored article

    Returns:
        Classification domain model ready for ClassificationRepository

    Example:
        >>> # After storing article
        >>> stored_article = await article_repo.insert_article(conn, article)
        >>>
        >>> # Convert each classification result
        >>> classifications = [
        ...     classification_result_to_classification(result, stored_article.id)
        ...     for result in classification_results
        ... ]
    """
    return Classification(
        article_id=article_id,
        classifier_type=result.classifier_type.value,  # Convert enum to string
        confidence_score=result.confidence,
        reasoning=result.reasoning,
        classified_at=datetime.now(timezone.utc),
        model_name=result.model_name,
        # Defaults for verification fields
        is_verified=False,
        verified_at=None,
        verified_by=None,
    )
