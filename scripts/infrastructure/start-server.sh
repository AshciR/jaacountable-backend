#!/bin/bash
# Start the FastAPI development server

set -e  # Exit on error

uv run fastapi dev src/server/app.py
