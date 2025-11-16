from datetime import datetime
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
    fetched_at: datetime = Field(default_factory=datetime.now)
    full_text: str | None = None

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
