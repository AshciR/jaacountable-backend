#!/bin/bash
# Load seed data into local development database.
#
# Prerequisite: database running and migrated.
#   ./scripts/infrastructure/init-db.sh
#
# Usage:
#   ./scripts/infrastructure/seed_db.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEED_FILE="${SCRIPT_DIR}/seed.sql"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-postgres}"

if [ ! -f "${SEED_FILE}" ]; then
  echo "ERROR: seed.sql not found at ${SEED_FILE}"
  echo "Run: uv run python scripts/infrastructure/generate_seed.py"
  exit 1
fi

SIZE_KB=$(du -k "${SEED_FILE}" | cut -f1)
echo "Loading seed data (${SIZE_KB} KB)..."

docker exec -i "${POSTGRES_CONTAINER}" psql \
  --username=user \
  --dbname=jaacountable_db \
  < "${SEED_FILE}"

echo "Seed data loaded."
