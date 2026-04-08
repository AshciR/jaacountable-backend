#!/bin/bash
# Create S3 buckets in LocalStack.
#
# Reads credentials and bucket name from .env in the project root.
# Safe to run multiple times — skips buckets that already exist.
#
# Usage:
#   ./scripts/infrastructure/create-s3-buckets.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
if [ ! -f "${ENV_FILE}" ]; then
    echo "ERROR: .env file not found at ${ENV_FILE}"
    exit 1
fi

# Source only KEY=VALUE lines (skip comments and blank lines)
set -a
# shellcheck disable=SC1090
while IFS= read -r line; do
    # Skip blank lines and comments
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    export "$line" 2>/dev/null || true
done < "${ENV_FILE}"
set +a

# ---------------------------------------------------------------------------
# Resolve config (fall back to LocalStack defaults)
# ---------------------------------------------------------------------------
ENDPOINT="${S3_ENDPOINT_URL:-http://localhost:4566}"
BUCKET="${S3_BUCKET:-daily-articles-discovery}"
REGION="${S3_REGION:-us-east-1}"

export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY:-test}"
export AWS_DEFAULT_REGION="${REGION}"

echo "Creating S3 bucket '${BUCKET}' at ${ENDPOINT}..."

# create-bucket returns an error if the bucket already exists with a different
# owner, but for LocalStack (single-account) we treat any existing bucket as fine.
if aws s3api create-bucket \
    --bucket "${BUCKET}" \
    --endpoint-url "${ENDPOINT}" \
    --output text 2>&1 | grep -v "BucketAlreadyOwnedByYou"; then
    echo "✓ Bucket '${BUCKET}' ready"
else
    echo "✓ Bucket '${BUCKET}' already exists"
fi
