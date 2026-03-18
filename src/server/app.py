"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config.database import db_config
from src.server.articles.router import router as articles_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_config.create_pool()
    app.state.db_config = db_config
    yield
    await db_config.close_pool()


app = FastAPI(lifespan=lifespan)
app.include_router(articles_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "Hello World"}
