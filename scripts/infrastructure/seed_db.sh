#!/bin/bash
# Load seed data into a database.
#
# Prerequisite: database running and migrated.
#   ./scripts/infrastructure/init-db.sh
#
# Usage:
#   ./scripts/infrastructure/seed_db.sh              # local Docker (default)
#   ./scripts/infrastructure/seed_db.sh .staging.env # remote (e.g. Supabase)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEED_FILE="${SCRIPT_DIR}/seed.sql"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-postgres}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:17-alpine}"

if [ ! -f "${SEED_FILE}" ]; then
  echo "ERROR: seed.sql not found at ${SEED_FILE}"
  echo "Run: uv run python scripts/infrastructure/generate_seed.py"
  exit 1
fi

SIZE_KB=$(du -k "${SEED_FILE}" | cut -f1)

ENV_FILE="${1:-}"

if [ -n "${ENV_FILE}" ]; then
  # Remote path: load DATABASE_URL from env file and connect via a throwaway Docker container
  if [ ! -f "${ENV_FILE}" ]; then
    echo "ERROR: env file '${ENV_FILE}' not found"
    exit 1
  fi

  export $(cat "${ENV_FILE}" | grep -v '^#' | xargs)

  if [ -z "${DATABASE_URL}" ]; then
    echo "ERROR: DATABASE_URL not set in ${ENV_FILE}"
    exit 1
  fi

  # Strip +asyncpg driver prefix — psql doesn't understand it
  PSQL_URL="${DATABASE_URL/+asyncpg/}"

  echo "Checking connectivity to remote database..."
  docker run --rm ${POSTGRES_IMAGE} psql "${PSQL_URL}" --command "SELECT 1" > /dev/null
  echo "Connection OK."

  echo "Loading seed data (${SIZE_KB} KB)..."
  docker run --rm -i ${POSTGRES_IMAGE} psql "${PSQL_URL}" < "${SEED_FILE}"
else
  # Local path: use the running Docker postgres container
  echo "Loading seed data (${SIZE_KB} KB)..."
  docker exec -i "${POSTGRES_CONTAINER}" psql \
    --username=user \
    --dbname=jaacountable_db \
    < "${SEED_FILE}"
fi

echo "Seed data loaded."
