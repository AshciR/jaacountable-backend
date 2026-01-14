#!/bin/bash
# Run Alembic database migrations
#
# Usage:
#   ./scripts/infrastructure/migrate.sh              # Uses .env (default)
#   ./scripts/infrastructure/migrate.sh .staging.env # Uses .staging.env
#   ./scripts/infrastructure/migrate.sh .production.env # Uses .production.env

set -e  # Exit on error

# Determine which environment file to use
ENV_FILE="${1:-.env}"

# Load environment variables from the specified file
if [ -f "$ENV_FILE" ]; then
    echo "Loading environment variables from $ENV_FILE..."
    export $(cat "$ENV_FILE" | grep -v '^#' | xargs)
else
    echo "WARNING: Environment file '$ENV_FILE' not found"
    echo "Proceeding with existing environment variables..."
fi

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL environment variable is not set"
    echo ""
    echo "Usage:"
    echo "  ./scripts/infrastructure/migrate.sh              # Uses .env (default)"
    echo "  ./scripts/infrastructure/migrate.sh .staging.env # Uses .staging.env"
    echo ""
    echo "Or set DATABASE_URL in your environment before running this script"
    exit 1
fi

echo "Running database migrations..."
alembic upgrade head

echo "✓ Migrations completed successfully"
