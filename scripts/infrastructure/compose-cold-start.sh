#!/bin/bash
# Cold start the docker-compose stack from scratch.
#
# Tears down existing containers and volumes, runs migrations, optionally
# seeds the database, then starts the app.
#
# Usage:
#   ./scripts/infrastructure/compose-cold-start.sh
#   SEED_DB=true ./scripts/infrastructure/compose-cold-start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Cold starting docker-compose stack..."
echo ""

echo "Tearing down existing containers and volumes..."
docker-compose down -v
echo ""

"${SCRIPT_DIR}/start-db.sh"
echo ""

"${SCRIPT_DIR}/migrate.sh"
echo ""
echo "✓ Migrations complete"

if [ "${SEED_DB}" = "true" ]; then
  echo ""
  echo "SEED_DB=true: Loading seed data..."
  "${SCRIPT_DIR}/seed_db.sh"
  echo "✓ Seed complete"
fi

echo ""
echo "Starting Redis and app..."
docker-compose up -d --build app
