#!/bin/bash
# Start LocalStack container and wait for it to be healthy

set -e  # Exit on error

echo "Starting LocalStack container..."
docker-compose up -d localstack

echo "Waiting for LocalStack to be healthy..."
timeout=60
elapsed=0

while [ $elapsed -lt $timeout ]; do
    if docker-compose ps localstack | grep -q "healthy"; then
        echo "✓ LocalStack is ready!"
        exit 0
    fi

    echo -n "."
    sleep 2
    elapsed=$((elapsed + 2))
done

echo ""
echo "ERROR: LocalStack failed to become healthy within ${timeout} seconds"
echo "Check logs with: docker-compose logs localstack"
exit 1
