#!/bin/bash
# Run Alembic database migrations

set -e  # Exit on error

# Load environment variables from .env if it exists
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL environment variable is not set"
    echo "Please create a .env file with DATABASE_URL or set it in your environment"
    exit 1
fi

echo "Running database migrations..."
alembic upgrade head

echo "✓ Migrations completed successfully"
