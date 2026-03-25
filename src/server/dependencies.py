"""Shared FastAPI dependencies."""
from typing import AsyncGenerator, Any

import asyncpg
from fastapi import Request

from src.analytics.client import AnalyticsClient
from src.cache.cache_interface import CacheBackend


async def get_db(request: Request) -> AsyncGenerator[asyncpg.Connection, Any]:
    async with request.app.state.db_config.connection() as conn:
        yield conn


def get_analytics(request: Request) -> AnalyticsClient:
    """Return the shared AnalyticsClient from application state.

    If analytics is disabled (no API key configured), the returned client
    silently drops all events — callers do not need to check disabled state.
    """
    return request.app.state.analytics_client


def get_cache(request: Request) -> CacheBackend:
    """Return the shared CacheBackend from application state."""
    return request.app.state.cache

