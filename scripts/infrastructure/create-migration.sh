#!/bin/bash
# Create a new Alembic migration file

set -e  # Exit on error

if [ -z "$1" ]; then
    echo "ERROR: Migration message is required"
    echo "Usage: $0 \"migration message\""
    echo "Example: $0 \"add classifications table\""
    exit 1
fi

MESSAGE="$1"

echo "Creating new migration: $MESSAGE"
alembic revision -m "$MESSAGE"

echo ""
echo "✓ Migration file created successfully"
echo ""
echo "Next steps:"
echo "1. Edit the migration file in alembic/versions/"
echo "2. Add your SQL DDL to the upgrade() and downgrade() functions"
echo "3. Run migrations with: ./scripts/migrate.sh"
