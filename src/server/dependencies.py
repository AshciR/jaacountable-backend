"""Shared FastAPI dependencies."""
from typing import AsyncGenerator, Any

import asyncpg
from fastapi import Request


async def get_db(request: Request) -> AsyncGenerator[asyncpg.Connection, Any]:
    async with request.app.state.db_config.connection() as conn:
        yield conn

