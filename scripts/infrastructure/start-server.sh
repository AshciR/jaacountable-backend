#!/bin/bash
# Start the FastAPI development server

set -e  # Exit on error

# Load .env so env vars (e.g. POSTHOG_API_KEY) are available to the server
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

uv run fastapi dev src/server/app.py
