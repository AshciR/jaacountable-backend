"""HTTP router for the articles domain."""
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, Query, Request

from src.analytics.client import AnalyticsClient
from src.server.articles.schemas import (
    ArticleSearchParams,
    ArticleSearchResponse,
    ArticleSearchResultSchema,
)
from src.cache.cache_interface import CacheBackend
from src.server.articles.service import ArticleSearchService
from src.server.dependencies import get_analytics, get_cache, get_db

router = APIRouter(prefix="/articles", tags=["articles"])


def _get_service(cache: Annotated[CacheBackend, Depends(get_cache)]) -> ArticleSearchService:
    return ArticleSearchService(cache=cache)


@router.get("", response_model=ArticleSearchResponse)
async def search_articles(
    request: Request,
    params: Annotated[ArticleSearchParams, Query()],
    conn: Annotated[asyncpg.Connection, Depends(get_db)],
    service: Annotated[ArticleSearchService, Depends(_get_service)],
    analytics: Annotated[AnalyticsClient, Depends(get_analytics)],
) -> ArticleSearchResponse:
    results, total = await service.search(conn, params)

    analytics.capture_with_common_props(
        distinct_id=analytics.get_distinct_id(request),
        event="search:query_submit",
        properties={"search_query": params.q, "results_count": total},
        is_internal=analytics.is_internal_request(request),
    )

    return ArticleSearchResponse.build(
        items=[ArticleSearchResultSchema.model_validate(r) for r in results],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )
