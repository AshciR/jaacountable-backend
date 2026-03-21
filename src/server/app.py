"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config.database import db_config
from config.log_config import configure_logging
from src.server.articles.router import router as articles_router
from src.server.entities.router import router as entities_router
from src.server.middleware import CanonicalLogMiddleware

API_V1_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_config.create_pool()
    app.state.db_config = db_config
    yield
    await db_config.close_pool()


configure_logging()

app = FastAPI(lifespan=lifespan)

# Middlewares
app.add_middleware(CanonicalLogMiddleware)

# Routers
app.include_router(articles_router, prefix=API_V1_PREFIX)
app.include_router(entities_router, prefix=API_V1_PREFIX)


@app.get("/")
async def root():
    return {"message": "Hello World"}
