"""HTTP router for the articles domain."""
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, Query

from src.server.articles.schemas import (
    ArticleSearchParams,
    ArticleSearchResponse,
    ArticleSearchResultSchema,
)
from src.server.articles.service import ArticleSearchService
from src.server.dependencies import get_db

router = APIRouter(prefix="/articles", tags=["articles"])


def _get_service() -> ArticleSearchService:
    return ArticleSearchService()


@router.get("", response_model=ArticleSearchResponse)
async def search_articles(
    params: Annotated[ArticleSearchParams, Query()],
    conn: Annotated[asyncpg.Connection, Depends(get_db)],
    service: Annotated[ArticleSearchService, Depends(_get_service)],
) -> ArticleSearchResponse:
    results, total = await service.search(conn, params)
    return ArticleSearchResponse.build(
        items=[ArticleSearchResultSchema.model_validate(r) for r in results],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )
