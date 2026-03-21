"""Shared FastAPI dependencies."""
from typing import AsyncGenerator, Any

import asyncpg
from fastapi import Request

from src.analytics.client import AnalyticsClient


async def get_db(request: Request) -> AsyncGenerator[asyncpg.Connection, Any]:
    async with request.app.state.db_config.connection() as conn:
        yield conn


def get_analytics(request: Request) -> AnalyticsClient:
    """Return the shared AnalyticsClient from application state.

    If analytics is disabled (no API key configured), the returned client
    silently drops all events — callers do not need to check disabled state.
    """
    return request.app.state.analytics_client

