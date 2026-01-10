# Batch Article Classification Script

Production-ready script for processing discovered articles through the full orchestration pipeline: **Extract → Classify → Store**.

## Overview

`process_articles_batch.py` reads article URLs from JSONL files (output from discovery scripts) and processes them through the complete classification pipeline. It features robust error handling, resume capability, dry-run mode, and real-time progress tracking.

## Features

- **Resume Capability**: Skip already-processed URLs with `--skip-existing`
- **Dry-run Mode**: Test classification without database writes using `--dry-run`
- **Configurable Concurrency**: Process 1-10 articles in parallel
- **Real-time Progress**: Live statistics table and progress bar
- **Comprehensive Reporting**: JSON summary + error JSONL files
- **Fail-soft Error Handling**: Individual failures don't crash entire batch
- **Performance Tracking**: Articles/second, success rates, relevance rates

## Prerequisites

- Python 3.12+
- PostgreSQL database running
- `DATABASE_URL` environment variable set
- JSONL input file with discovered articles (from discovery scripts)

## Quick Start

```bash
# Test with 20 articles
head -20 scripts/production/discovery/output/gleaner_archive_2021_11-11.jsonl > test_batch_20.jsonl
uv run python scripts/production/classification/process_articles_batch.py --input test_batch_20.jsonl

# Production run with skip-existing
uv run python scripts/production/classification/process_articles_batch.py \
    --input scripts/production/discovery/output/gleaner_archive_2021_11-11.jsonl \
    --concurrency 10 \
    --skip-existing
```

## CLI Options

### Required

- `--input FILE` - Path to JSONL file with discovered articles

### Optional

- `--concurrency N` - Max concurrent workers (default: 4, range: 1-10)
- `--skip-existing` - Pre-query DB for existing URLs and skip them
- `--dry-run` - Classify articles but don't store (transaction rollback)
- `--min-confidence FLOAT` - Relevance threshold (default: 0.7, range: 0.0-1.0)
- `--output-dir DIR` - Results directory (default: `scripts/production/classification/output`)

## Input Format

The script expects a JSONL file where each line is a `DiscoveredArticle` object:

```json
{
  "url": "https://gleaner.newspaperarchive.com/kingston-gleaner/2021-11-01/page-3/",
  "news_source_id": 1,
  "section": "archive",
  "discovered_at": "2026-01-08T00:00:00Z",
  "title": "Kingston Gleaner Newspaper Archives | Nov 01, 2021, p. 3",
  "published_date": "2021-11-01T00:00:00Z"
}
```

## Output Files

All outputs are placed in `scripts/production/classification/output/`:

### JSON Summary Report
**Location**: `output/batch_results/batch_{timestamp}.json`

```json
{
  "metadata": {
    "timestamp": "2026-01-13T20:05:43.952397+00:00",
    "input_file": "test_batch_100.jsonl",
    "dry_run": false,
    "concurrency": 10,
    "min_confidence": 0.7,
    "skip_existing": true
  },
  "summary": {
    "total_articles": 99,
    "processed": 99,
    "extracted": 99,
    "classified": 99,
    "relevant": 9,
    "stored": 9,
    "duplicates": 0,
    "skipped_existing": 1,
    "total_errors": 0
  },
  "errors_by_category": {
    "extraction": 0,
    "classification": 0,
    "storage": 0,
    "other": 0
  },
  "performance": {
    "elapsed_seconds": 217.26,
    "articles_per_second": 0.46
  },
  "outcomes": {
    "success_rate": "100.0%",
    "relevance_rate": "9.1%",
    "storage_rate": "9.1%"
  }
}
```

### Error Log (JSONL)
**Location**: `output/batch_results/batch_{timestamp}_errors.jsonl`

Each line contains details about a failed article:

```json
{
  "url": "https://example.com/article",
  "section": "archive",
  "error_category": "extraction",
  "error_message": "HTTP 404 Not Found",
  "extracted": false,
  "classified": false,
  "relevant": false,
  "stored": false,
  "timestamp": "2026-01-08T15:32:10.456Z"
}
```

### Detailed Log
**Location**: `output/logs/batch_processing_{timestamp}.log`

Structured logging with:
- Extraction progress
- Classification results
- Entity normalization cache stats
- Database operations
- Canonical-log-line telemetry (visible with `LOG_JSON=true`)

## Usage Examples

### 1. Dry-run Test (No Database Writes)

```bash
uv run python scripts/production/classification/process_articles_batch.py \
    --input test_batch_20.jsonl \
    --dry-run \
    --concurrency 2
```

**Expected**: All articles classified, `stored: 0` in report (transaction rollback)

### 2. Normal Mode (Production)

```bash
uv run python scripts/production/classification/process_articles_batch.py \
    --input test_batch_100.jsonl \
    --concurrency 10
```

**Expected**: Relevant articles stored in database

### 3. Resume Capability

```bash
# First run: Process 100 articles, store ~5-15 relevant ones
uv run python scripts/production/classification/process_articles_batch.py \
    --input test_batch_100.jsonl \
    --concurrency 10

# Second run: Skip already-processed URLs
uv run python scripts/production/classification/process_articles_batch.py \
    --input test_batch_100.jsonl \
    --concurrency 10 \
    --skip-existing
```

**Expected**: Second run skips URLs from first run

### 4. Custom Confidence Threshold

```bash
uv run python scripts/production/classification/process_articles_batch.py \
    --input test_batch_100.jsonl \
    --min-confidence 0.8 \
    --concurrency 10
```

**Expected**: Only articles with ≥0.8 confidence stored (lower relevance rate)

### 5. Enable JSON Logging

```bash
LOG_JSON=true uv run python scripts/production/classification/process_articles_batch.py \
    --input test_batch_100.jsonl \
    --concurrency 10
```

**Expected**: Logs show structured JSON with telemetry data (canonical-log-line)

## Performance Benchmarks

| Batch Size | Concurrency | Time      | Rate          | Relevant | Errors |
|------------|-------------|-----------|---------------|----------|--------|
| 20         | 2           | ~340s     | 0.06/sec      | 2 (10%)  | 0      |
| 20         | 10          | ~138s     | 0.14/sec      | 1 (5%)   | 0      |
| 100        | 10          | ~217s     | 0.46/sec      | 9 (9%)   | 0      |

**Expected Performance**:
- **Articles/second**: 0.3-0.6 (depending on concurrency)
- **Relevance rate**: 5-15% (varies by content)
- **Extraction error rate**: <5%
- **Classification error rate**: <2%

## Error Handling

The script uses **fail-soft** error handling:

1. **Extraction errors** (HTTP failures, parsing issues) → Skip article, continue processing
2. **Classification errors** (LLM API failures) → Skip article, continue processing
3. **Storage errors** (DB constraint violations) → Skip article, continue processing
4. **Other errors** (unexpected exceptions) → Log error, continue processing

All errors are:
- Logged to `batch_processing_{timestamp}.log`
- Categorized in JSON summary report
- Listed in `batch_{timestamp}_errors.jsonl` for debugging

## Testing Workflow

### Phase 1: Small Batch (20 articles)

```bash
# 1. Create test file
head -20 scripts/production/discovery/output/gleaner_archive_2021_11-11.jsonl > test_batch_20.jsonl

# 2. Dry-run test
uv run python scripts/production/classification/process_articles_batch.py \
    --input test_batch_20.jsonl \
    --dry-run \
    --concurrency 2

# 3. Normal mode
uv run python scripts/production/classification/process_articles_batch.py \
    --input test_batch_20.jsonl \
    --concurrency 10

# 4. Test skip-existing
uv run python scripts/production/classification/process_articles_batch.py \
    --input test_batch_20.jsonl \
    --skip-existing \
    --concurrency 10
```

### Phase 2: Medium Batch (100 articles)

```bash
head -100 scripts/production/discovery/output/gleaner_archive_2021_11-11.jsonl > test_batch_100.jsonl

uv run python scripts/production/classification/process_articles_batch.py \
    --input test_batch_100.jsonl \
    --concurrency 10 \
    --skip-existing
```

### Phase 3: Production Batch (561 articles)

```bash
uv run python scripts/production/classification/process_articles_batch.py \
    --input scripts/production/discovery/output/gleaner_archive_2021_11-11.jsonl \
    --concurrency 10 \
    --skip-existing
```

## Troubleshooting

### Issue: "Input file does not exist"
**Solution**: Ensure path is correct. Use `--input test_batch_20.jsonl` (relative) or full path.

### Issue: "Database connection failed"
**Solution**: Check `DATABASE_URL` in `.env` file and ensure PostgreSQL is running.

### Issue: "Concurrency must be between 1 and 10"
**Solution**: Use `--concurrency` value between 1-10. Higher values risk rate limiting.

### Issue: Logs show "canonical-log-line" but no data
**Solution**: Structured data only visible in JSON mode. Use `LOG_JSON=true` to see telemetry.

### Issue: Low relevance rate (<2%)
**Solution**: Check article content quality. Archive pages may have less relevant content than current news.

### Issue: High extraction error rate (>10%)
**Solution**: Check network connectivity and archive.org availability. Some URLs may be broken.

## Architecture Notes

### Concurrency Model

- **Semaphore**: Limits concurrent tasks to `--concurrency` value
- **Connection Pool**: Size = 2× concurrency to prevent exhaustion
- **asyncio.gather**: Collects results from all concurrent tasks

### Resume Capability

- Uses **single batch query**: `SELECT url FROM articles WHERE url = ANY($1::text[])`
- **60x-600x faster** than individual queries for large batches
- Pre-filters articles before processing (not checked during processing)

### Dry-run Mode

- Uses **explicit transaction rollback** pattern
- Processing succeeds, but `await tx.rollback()` prevents database writes
- Useful for testing classification without polluting database

### Statistics Tracking

- **Thread-safe**: `asyncio.Lock` for concurrent updates
- **Real-time**: Updated every 0.5 seconds during processing
- **Comprehensive**: Tracks extraction, classification, storage, errors, performance

## Related Scripts

- `scripts/production/discovery/discover_gleaner_archive_articles.py` - Archive discovery (produces input JSONL)
- `scripts/production/discovery/parallel_archive_discovery.py` - Parallel month discovery
- `scripts/validation/validate_pipeline_with_caching.py` - Single-article pipeline testing

## Environment Variables

- `DATABASE_URL` - PostgreSQL connection string (required)
- `LOG_JSON` - Enable JSON logging (optional, default: `false`)
- `OPENAI_API_KEY` - Required for classification (set in `.env`)

## Support

For issues or questions:
1. Check logs in `output/logs/batch_processing_{timestamp}.log`
2. Review error JSONL in `output/batch_results/batch_{timestamp}_errors.jsonl`
3. Verify database connectivity and article URLs
4. Test with smaller batch first (`--input test_batch_20.jsonl`)
