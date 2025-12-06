"""
Model conversion utilities for orchestration workflow.

Converts between service layer models and database domain models.
"""
from datetime import datetime, timezone

from src.article_extractor.models import ExtractedArticleContent
from src.article_classification.models import (
    ClassificationInput,
    ClassificationResult,
)
from src.article_persistence.models.domain import Article, Classification


def extracted_content_to_classification_input(
    extracted: ExtractedArticleContent,
    url: str,
    section: str
) -> ClassificationInput:
    """
    Convert ExtractedArticleContent to ClassificationInput.

    Combines extracted content with context from discovery.

    Args:
        extracted: Content from ArticleExtractionService
        url: Original article URL
        section: Article section/category (e.g., "news", "lead-stories")

    Returns:
        ClassificationInput ready for ClassificationService

    Example:
        >>> extracted = extractor.extract_article_content(url)
        >>> classification_input = extracted_content_to_classification_input(
        ...     extracted=extracted,
        ...     url=url,
        ...     section="news"
        ... )
    """
    return ClassificationInput(
        url=url,
        title=extracted.title,
        section=section,
        full_text=extracted.full_text,
        published_date=extracted.published_date,
    )


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


def filter_relevant_classifications(
    results: list[ClassificationResult],
    min_confidence: float = 0.7
) -> list[ClassificationResult]:
    """
    Filter classification results to only relevant articles.

    An article is relevant if AT LEAST ONE classifier marks it as:
    - is_relevant = True
    - confidence >= min_confidence

    Args:
        results: Classification results from ClassificationService
        min_confidence: Minimum confidence threshold (default: 0.7)

    Returns:
        List of relevant classification results (may be empty)

    Example:
        >>> # Only store if relevant
        >>> relevant = filter_relevant_classifications(
        ...     results=classification_results,
        ...     min_confidence=0.7
        ... )
        >>> if relevant:
        ...     # Store article and classifications
        ...     pass
    """
    return [
        result
        for result in results
        if result.is_relevant and result.confidence >= min_confidence
    ]
