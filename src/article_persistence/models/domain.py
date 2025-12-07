from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator, ConfigDict


class Article(BaseModel):
    """
    Pydantic model for Article data validation and serialization.

    Maps to the 'articles' database table schema.
    """
    id: int | None = None
    url: str
    title: str
    section: str
    published_date: datetime | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    full_text: str | None = None
    news_source_id: int

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


class Classification(BaseModel):
    """
    Pydantic model for Classification data validation and serialization.

    Maps to the 'classifications' database table schema.
    Represents an AI classification result for an article.
    """
    id: int | None = None
    article_id: int
    classifier_type: str
    confidence_score: float
    reasoning: str | None = None
    classified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_name: str
    is_verified: bool = False
    verified_at: datetime | None = None
    verified_by: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator('confidence_score')
    @classmethod
    def validate_confidence_score(cls, v: float) -> float:
        """Validate that confidence_score is between 0.0 and 1.0."""
        if v < 0.0 or v > 1.0:
            raise ValueError('Confidence score must be between 0.0 and 1.0')
        return v

    @field_validator('classifier_type', 'model_name')
    @classmethod
    def validate_required_string(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()


class NewsSource(BaseModel):
    """
    Pydantic model for NewsSource data validation and serialization.

    Maps to the 'news_sources' database table schema.
    Represents a news source that articles are scraped from.
    """
    id: int | None = None
    name: str
    base_url: str
    crawl_delay: int = 10
    is_active: bool = True
    last_scraped_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True)

    @field_validator('name', 'base_url')
    @classmethod
    def validate_required_string(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()

    @field_validator('crawl_delay')
    @classmethod
    def validate_crawl_delay(cls, v: int) -> int:
        """Validate that crawl_delay is positive."""
        if v < 0:
            raise ValueError('Crawl delay must be non-negative')
        return v


class ArticleStorageResult(BaseModel):
    """
    Result of storing an article with classifications.

    This model represents the outcome of a store operation,
    including whether the article was stored or already existed,
    and metadata about the storage operation.

    Attributes:
        stored: True if article was newly stored, False if duplicate
        article_id: Database ID of stored article, None if duplicate
        classification_count: Number of classifications stored with article
        article: Full Article model if stored, None if duplicate
        classifications: List of Classification models stored with article
    """
    stored: bool
    article_id: int | None
    classification_count: int
    article: Article | None
    classifications: list[Classification]

    model_config = ConfigDict(from_attributes=True)
