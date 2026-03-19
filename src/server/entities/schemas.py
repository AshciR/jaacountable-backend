"""API schemas for the entities domain."""
import math
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class EntityListParams(BaseModel):
    """Query parameters for the entity list endpoint."""

    sort: Literal["latest", "most_found"] = "latest"
    since: date | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class EntitySummarySchema(BaseModel):
    """Single entity result returned by the list endpoint."""

    name: str
    normalized_name: str
    article_count: int
    last_seen_date: datetime

    model_config = ConfigDict(from_attributes=True, alias_generator=to_camel, populate_by_name=True)


class EntityListResponse(BaseModel):
    """Paginated entity list response."""

    items: list[EntitySummarySchema]
    total: int
    page: int
    page_size: int
    pages: int

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @classmethod
    def build(
        cls,
        items: list[EntitySummarySchema],
        total: int,
        page: int,
        page_size: int,
    ) -> "EntityListResponse":
        pages = math.ceil(total / page_size) if total else 0
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)
