"""FastAPI application entry point."""
import os
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from sentry_sdk.integrations.logging import LoggingIntegration

from config.database import db_config
from config.log_config import configure_logging, logger
from src.analytics.client import analytics_client
from src.server.articles.router import router as articles_router
from src.server.entities.router import router as entities_router
from src.server.middleware import CanonicalLogMiddleware

API_V1_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_config.create_pool()
    app.state.db_config = db_config
    app.state.analytics_client = analytics_client
    yield
    await db_config.close_pool()
    analytics_client.shutdown()


def _init_sentry() -> None:
    """
    Initialize Sentry
    """
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        logger.warning("Telemetry not initialized: SENTRY_DSN is not set")
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("APP_ENV", "development"),
        send_default_pii=True,
        enable_logs=True,
        integrations=[
            # Disable stdlib log → Sentry Logs capture; LoguruIntegration handles it instead.
            # Without this, every stdlib log (e.g. uvicorn) is captured twice:
            # once via LoggingIntegration (auto.log.stdlib) and once via
            # InterceptHandler → loguru → LoguruIntegration (auto.log.loguru).
            LoggingIntegration(sentry_logs_level=None),
        ],
    )
    logger.info("Telemetry initialized")


configure_logging()
_init_sentry()

app = FastAPI(lifespan=lifespan)

# Middlewares
app.add_middleware(CanonicalLogMiddleware)

# Routers
app.include_router(articles_router, prefix=API_V1_PREFIX)
app.include_router(entities_router, prefix=API_V1_PREFIX)
