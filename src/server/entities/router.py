"""HTTP router for the entities domain."""
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, Query

from src.server.entities.schemas import (
    EntityListParams,
    EntityListResponse,
    EntitySummarySchema,
)
from src.cache.cache_interface import CacheBackend
from src.server.entities.service import EntityListService
from src.server.dependencies import get_cache, get_db

router = APIRouter(prefix="/entities", tags=["entities"])


def _get_service(cache: Annotated[CacheBackend, Depends(get_cache)]) -> EntityListService:
    return EntityListService(cache=cache)


@router.get("", response_model=EntityListResponse)
async def list_entities(
    params: Annotated[EntityListParams, Query()],
    conn: Annotated[asyncpg.Connection, Depends(get_db)],
    service: Annotated[EntityListService, Depends(_get_service)],
) -> EntityListResponse:
    results, total = await service.list_entities(conn, params)
    return EntityListResponse.build(
        items=[EntitySummarySchema.model_validate(r) for r in results],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )
