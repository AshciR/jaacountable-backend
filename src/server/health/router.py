"""Health check endpoint."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    database: str


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> JSONResponse:
    try:
        async with request.app.state.db_config.connection() as conn:
            await conn.fetchval("SELECT 1")
        return JSONResponse({"status": "ok", "database": "ok"}, status_code=200)
    except Exception:
        return JSONResponse(
            {"status": "degraded", "database": "error"}, status_code=503
        )
