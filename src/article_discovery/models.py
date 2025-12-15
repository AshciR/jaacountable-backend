"""Article discovery models."""
from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel, field_validator, ConfigDict


@dataclass
class RssFeedConfig:
    """
    Configuration for a single RSS feed.

    Used to configure RSS feed discoverers with multiple feeds,
    where each feed maps to a different section.

    Attributes:
        url: RSS feed URL
        section: Section name to assign to discovered articles from this feed
    """

    url: str
    section: str


class DiscoveredArticle(BaseModel):
    """
    Article discovered from a news source.

    This model represents the minimal metadata needed to pass an article
    from the discovery layer to the extraction layer. Discovery identifies
    article URLs and basic metadata without fetching full content.

    Workflow Position:
        Discovery → **DiscoveredArticle** → Extraction → Classification → Storage

    Integration Point:
        The orchestration layer receives DiscoveredArticle instances and calls:

        >>> discovered = await discovery_service.discover(news_source_id=1)
        >>> for article in discovered:
        ...     result = await orchestration_service.process_article(
        ...         conn=conn,
        ...         url=article.url,
        ...         section=article.section,
        ...         news_source_id=article.news_source_id,
        ...     )

    Design Notes:
        - No article_id (discovery happens before storage)
        - Minimal metadata (extraction service will fetch full content)
        - URL is the unique identifier at this stage
    """

    url: str
    news_source_id: int
    section: str
    discovered_at: datetime

    # Optional metadata (if available during discovery)
    title: str | None = None
    published_date: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate that url is not empty and has proper URL structure."""
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

    @field_validator("news_source_id")
    @classmethod
    def validate_news_source_id(cls, v: int) -> int:
        """Validate that news_source_id is positive."""
        if v <= 0:
            raise ValueError("News source ID must be positive")
        return v

    @field_validator("discovered_at")
    @classmethod
    def validate_discovered_at(cls, v: datetime) -> datetime:
        """Validate that discovered_at is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("Discovered timestamp must be timezone-aware")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        """Validate and normalize title field."""
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

        if v.tzinfo is None:
            raise ValueError("Published date must be timezone-aware")

        return v
