#!/bin/bash
# Cold start the docker-compose stack from scratch.
#
# Tears down existing containers and volumes, runs migrations, optionally
# seeds the database, then starts the app.
#
# Usage:
#   ./scripts/infrastructure/compose-cold-start.sh
#   SEED_DB=true ./scripts/infrastructure/compose-cold-start.sh
#   ./scripts/infrastructure/compose-cold-start.sh --replicas 2
#   SEED_DB=true ./scripts/infrastructure/compose-cold-start.sh --replicas 3

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
REPLICAS=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --replicas)
      REPLICAS="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--replicas N]"
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Build compose file list (scale override only needed for >1 replica)
# ---------------------------------------------------------------------------
COMPOSE_FILES="-f docker-compose.yml"
if [ "$REPLICAS" -gt 1 ]; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.scale.yml"
fi

echo "Cold starting docker-compose stack..."
[ "$REPLICAS" -gt 1 ] && echo "Replicas: $REPLICAS"
echo ""

echo "Tearing down existing containers and volumes..."
docker compose $COMPOSE_FILES down -v
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
echo "Starting LocalStack..."
"${SCRIPT_DIR}/start-localstack.sh"

echo ""
echo "Provisioning S3 buckets..."
"${SCRIPT_DIR}/create-s3-buckets.sh"

echo ""
echo "Starting Redis and app..."
docker compose $COMPOSE_FILES up -d --build --scale app="$REPLICAS" app

# Print host ports when running multiple replicas
if [ "$REPLICAS" -gt 1 ]; then
  echo ""
  echo "App replicas listening on:"
  docker compose $COMPOSE_FILES ps --format "table {{.Name}}\t{{.Ports}}" app
fi
