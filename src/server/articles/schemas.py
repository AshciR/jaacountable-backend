"""API schemas for the articles domain."""
import math
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ArticleSearchParams(BaseModel):
    """Query parameters for the article search endpoint."""

    q: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    include_full_text: bool = False
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    sort: Literal["relevance", "published_date"] = "relevance"
    order: Literal["asc", "desc"] = "desc"


class SearchClassificationSchema(BaseModel):
    """Classification summary embedded in a search result."""

    classifier_type: str
    confidence_score: float

    model_config = ConfigDict(from_attributes=True)


class ArticleSearchResultSchema(BaseModel):
    """Single article result returned by the search endpoint."""

    public_id: UUID
    url: str
    title: str
    section: str
    published_date: datetime | None
    news_source_id: int
    snippet: str | None
    entities: list[str]
    classifications: list[SearchClassificationSchema]
    full_text: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ArticleSearchResponse(BaseModel):
    """Paginated article search response."""

    items: list[ArticleSearchResultSchema]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(
        cls,
        items: list[ArticleSearchResultSchema],
        total: int,
        page: int,
        page_size: int,
    ) -> "ArticleSearchResponse":
        pages = math.ceil(total / page_size) if total else 0
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)
