"""Model conversion utilities for classification workflow."""
from src.article_extractor.models import ExtractedArticleContent
from .models import ClassificationInput


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
