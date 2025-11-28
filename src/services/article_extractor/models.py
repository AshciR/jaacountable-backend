"""Article content models for extraction service."""
from datetime import datetime
from pydantic import BaseModel, field_validator, ConfigDict


class ExtractedArticleContent(BaseModel):
    """
    Structured article content extracted from news sources.

    This model represents the extracted content from an article,
    including metadata and full text. Used as the return type
    for all article extraction strategies.
    """

    title: str
    full_text: str
    author: str | None = None
    published_date: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate that title is not empty."""
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()

    @field_validator("full_text")
    @classmethod
    def validate_full_text(cls, v: str) -> str:
        """Validate that full_text is not empty and meets minimum length."""
        if not v or not v.strip():
            raise ValueError("Full text cannot be empty")

        stripped = v.strip()
        # Minimum 50 characters for meaningful content
        if len(stripped) < 50:
            raise ValueError("Full text must be at least 50 characters")

        return stripped

    @field_validator("author")
    @classmethod
    def validate_author(cls, v: str | None) -> str | None:
        """Validate and normalize author field."""
        if v is None:
            return None

        stripped = v.strip()
        if not stripped:
            return None

        return stripped

    @field_validator("published_date")
    @classmethod
    def validate_published_date(cls, v: datetime | None) -> datetime | None:
        """Validate that published_date is timezone-aware if provided."""
        if v is None:
            return None

        # Ensure timezone-aware datetime (consistent with existing patterns)
        if v.tzinfo is None:
            raise ValueError("Published date must be timezone-aware")

        return v
