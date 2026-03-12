#!/bin/bash
# Stop the database container and remove all data volumes.
# Leaves a clean slate so init-db.sh can start fresh.
#
# Usage:
#   ./scripts/infrastructure/clean-db.sh
#   ./scripts/infrastructure/clean-db.sh && ./scripts/infrastructure/init-db.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Stopping database and removing volumes..."
docker-compose -f "${SCRIPT_DIR}/../../docker-compose.yml" down -v

echo "✓ Database cleaned. Run ./scripts/infrastructure/init-db.sh to start fresh."
