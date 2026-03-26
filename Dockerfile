# =============================================================================
# Stage 1: builder
# Installs all Python dependencies using uv into /app/.venv
# =============================================================================
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifests first — layer cache skips re-install when only
# source code changes
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment.
# --frozen: use exact versions from uv.lock (reproducible builds)
# --no-install-project: skip installing the project package itself;
#   source is copied separately so bind-mount hot reload works cleanly
RUN uv sync --frozen --no-install-project

# =============================================================================
# Stage 2: runtime
# Lean production image — venv + application source only
# =============================================================================
FROM python:3.12-slim AS runtime

# Copy uv into runtime so `uv run` commands work identically to the host
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Non-root user required for Render and most cloud platforms
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

LABEL org.opencontainers.image.source="https://github.com/AshciR/jaacountable-backend"
LABEL org.opencontainers.image.description="Jaccountable, news aggregator for government accountability tracking"

# Copy pre-built venv from builder stage
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv

# Copy application source (tests/ and scripts/ excluded via .dockerignore)
COPY --chown=appuser:appgroup . .

# Add venv to PATH; disable Python output buffering and .pyc file creation
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

USER appuser

# Production entrypoint: fastapi run (uvicorn, no reload)
# Env vars (DATABASE_URL, OPENAI_API_KEY, etc.) are injected at runtime by
# Docker Compose locally, or by Render's Environment Variables in production.
CMD ["fastapi", "run", "src/server/app.py", "--host", "0.0.0.0", "--port", "8000"]
