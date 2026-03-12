#!/bin/bash
# Initialize database: start container and run migrations

set -e  # Exit on error

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Initializing database..."
echo ""

# Start database and wait for health check
"${SCRIPT_DIR}/start-db.sh"

echo ""

# Run migrations
"${SCRIPT_DIR}/migrate.sh"

echo ""
echo "✓ Database initialization complete"

# Optional: load seed data
# To opt in: SEED_DB=true ./scripts/infrastructure/init-db.sh
if [ "${SEED_DB}" = "true" ]; then
  echo ""
  echo "SEED_DB=true: Loading seed data..."
  "${SCRIPT_DIR}/seed_db.sh"
fi
