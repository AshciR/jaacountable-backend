"""Classification models for article classification service."""
from datetime import datetime
from pydantic import BaseModel, field_validator, ConfigDict


class ClassificationInput(BaseModel):
    """
    Input data for article classification agents.

    This model serves as the interface between the article extraction layer
    and the classification layer. It combines content from ExtractedArticleContent
    with contextual metadata from the scraper to provide all necessary information
    for AI-based relevance classification.

    Important: Classification happens BEFORE database storage, so article_id is
    not available at this stage. The URL serves as the unique identifier.

    Workflow:
        1. Extract article content from news source → ExtractedArticleContent
        2. Construct ClassificationInput (this model) from extraction + scraper context
        3. Classify to determine relevance → ClassificationResult
        4. If relevant, store article in database (article_id generated here)

    Example:
        >>> from datetime import datetime, timezone
        >>> # After extracting article content
        >>> url = "https://jamaica-gleaner.com/article/news/20251201/gov-announces-transparency"
        >>> section = "News"  # From scraper context
        >>> extracted = await extractor.extract(url)  # Returns ExtractedArticleContent
        >>>
        >>> # Construct classification input
        >>> classification_input = ClassificationInput(
        ...     url=url,
        ...     title=extracted.title,
        ...     section=section,
        ...     full_text=extracted.full_text,
        ...     published_date=extracted.published_date,
        ... )
        >>>
        >>> # Pass to classifier
        >>> result = await corruption_classifier.classify(classification_input)
        >>>
        >>> # Only store if relevant
        >>> if result.is_relevant:
        ...     # Store article and classification in database
        ...     pass
    """

    url: str
    title: str
    section: str
    full_text: str
    published_date: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate that url is not empty and has basic URL structure."""
        if not v or not v.strip():
            raise ValueError('URL cannot be empty')

        # Basic URL validation - must start with http:// or https://
        v = v.strip()
        if not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('URL must start with http:// or https://')

        return v

    @field_validator('title', 'section')
    @classmethod
    def validate_required_string(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()

    @field_validator('full_text')
    @classmethod
    def validate_full_text(cls, v: str) -> str:
        """Validate that full_text is not empty and meets minimum length."""
        if not v or not v.strip():
            raise ValueError('Full text cannot be empty')

        stripped = v.strip()
        # Minimum 50 characters for meaningful content
        if len(stripped) < 50:
            raise ValueError('Full text must be at least 50 characters')

        return stripped

    @field_validator('published_date')
    @classmethod
    def validate_published_date(cls, v: datetime | None) -> datetime | None:
        """Validate that published_date is timezone-aware if provided."""
        if v is None:
            return None

        # Ensure timezone-aware datetime (consistent with existing patterns)
        if v.tzinfo is None:
            raise ValueError('Published date must be timezone-aware')

        return v
