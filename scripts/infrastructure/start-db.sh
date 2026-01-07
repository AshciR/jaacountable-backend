#!/bin/bash
# Start PostgreSQL database container and wait for it to be healthy

set -e  # Exit on error

echo "Starting PostgreSQL container..."
docker-compose up -d postgres

echo "Waiting for PostgreSQL to be healthy..."
timeout=60
elapsed=0

while [ $elapsed -lt $timeout ]; do
    if docker-compose ps postgres | grep -q "healthy"; then
        echo "✓ PostgreSQL is ready!"
        exit 0
    fi

    echo -n "."
    sleep 2
    elapsed=$((elapsed + 2))
done

echo ""
echo "ERROR: PostgreSQL failed to become healthy within ${timeout} seconds"
echo "Check logs with: docker-compose logs postgres"
exit 1
