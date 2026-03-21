"""Canonical log line middleware for the API server."""
import time
from uuid import uuid4

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CanonicalLogMiddleware(BaseHTTPMiddleware):
    """Emit one structured log line per HTTP request.

    Collects telemetry throughout the request lifecycle and emits a single
    canonical log line at completion — even if an exception occurs.

    Log level reflects outcome:
    - ERROR   → 5xx status or unhandled exception
    - WARNING → 4xx status
    - INFO    → 2xx/3xx status
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid4())
        start = time.perf_counter()

        telemetry: dict = {
            "request_id": request_id,
            "http_method": request.method,
            "http_path": request.url.path,
            "http_status": None,
            "duration_ms": None,
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent", ""),
            "query_params": str(request.url.query) if request.url.query else "",
            "error": None,
            "error_type": None,
        }

        response: Response | None = None
        try:
            response = await call_next(request)
            telemetry["http_status"] = response.status_code
            response.headers["X-Request-Id"] = request_id
            return response
        except Exception as exc:
            telemetry["error"] = str(exc)
            telemetry["error_type"] = type(exc).__name__
            telemetry["http_status"] = 500
            raise
        finally:
            telemetry["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
            status = telemetry["http_status"] or 500
            try:
                if status >= 500 or telemetry["error"] is not None:
                    logger.bind(**telemetry).error("canonical-log-line")
                elif status >= 400:
                    logger.bind(**telemetry).warning("canonical-log-line")
                else:
                    logger.bind(**telemetry).info("canonical-log-line")
            except Exception:
                pass  # Never let logging failures affect the response
