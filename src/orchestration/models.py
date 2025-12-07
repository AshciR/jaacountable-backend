"""Orchestration models for pipeline results."""
from pydantic import BaseModel, field_validator, ConfigDict

from src.article_classification.models import ClassificationResult


class OrchestrationResult(BaseModel):
    """
    Result of processing an article through the full pipeline.

    This model tracks the outcome of each pipeline stage:
    Extract → Classify → Filter → Store

    The model supports both successful and failed processing,
    providing detailed information about what happened at each stage.

    Attributes:
        url: Article URL that was processed
        section: Article section/category
        extracted: Whether extraction succeeded
        classified: Whether classification was performed
        relevant: Whether article passed relevance threshold
        stored: Whether article was stored in database
        article_id: Database ID if stored, None otherwise
        classification_count: Number of classifications stored
        classification_results: All classification results (for transparency)
        error: Error message if processing failed, None otherwise

    Example - Successful processing:
        OrchestrationResult(
            url="https://example.com/article",
            section="news",
            extracted=True,
            classified=True,
            relevant=True,
            stored=True,
            article_id=42,
            classification_count=2,
            classification_results=[...],
            error=None,
        )

    Example - Article not relevant:
        OrchestrationResult(
            url="https://example.com/article",
            section="news",
            extracted=True,
            classified=True,
            relevant=False,
            stored=False,
            article_id=None,
            classification_count=0,
            classification_results=[...],
            error=None,
        )

    Example - Extraction failed:
        OrchestrationResult(
            url="https://example.com/article",
            section="news",
            extracted=False,
            classified=False,
            relevant=False,
            stored=False,
            article_id=None,
            classification_count=0,
            classification_results=[],
            error="Failed to extract article: HTTP 404 Not Found",
        )
    """

    url: str
    section: str
    extracted: bool
    classified: bool
    relevant: bool
    stored: bool
    article_id: int | None
    classification_count: int
    classification_results: list[ClassificationResult]
    error: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate that url is not empty and has basic URL structure."""
        if not v or not v.strip():
            raise ValueError("URL cannot be empty")

        # Basic URL validation - must start with http:// or https://
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")

        return v

    @field_validator("section")
    @classmethod
    def validate_section(cls, v: str) -> str:
        """Validate that section is not empty."""
        if not v or not v.strip():
            raise ValueError("Section cannot be empty")
        return v.strip()

    @field_validator("classification_count")
    @classmethod
    def validate_classification_count(cls, v: int) -> int:
        """Validate that classification_count is non-negative."""
        if v < 0:
            raise ValueError("Classification count must be non-negative")
        return v

    @field_validator("error")
    @classmethod
    def validate_error(cls, v: str | None) -> str | None:
        """Validate and normalize error field."""
        if v is None:
            return None

        stripped = v.strip()
        if not stripped:
            return None

        return stripped

    @field_validator("classification_results")
    @classmethod
    def validate_classification_results(
        cls, v: list[ClassificationResult]
    ) -> list[ClassificationResult]:
        """Validate that classification_results is a list (allow empty)."""
        if not isinstance(v, list):
            raise ValueError("Classification results must be a list")
        return v
