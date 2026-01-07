# Production Archive Discovery

Production-ready script for discovering articles from Jamaica Gleaner archives and exporting to JSONL format for pipeline ingestion.

## Overview

This script uses parallel workers to discover articles from historical archive pages and exports the results to JSONL files. It provides robust failure tracking with retry capabilities.

## Features

- **Parallel Discovery**: Uses multiple workers to discover articles from different months simultaneously
- **JSONL Export**: Standard JSON Lines format for easy pipeline ingestion
- **Failure Tracking**: Creates stub entries for failed months with retry information
- **Configurable**: Customizable worker count, crawl delay, and output directory
- **Respectful Crawling**: Configurable delay between requests (default: 0.5s)

## Usage

### Basic Usage

Discover 3 months (September-November 2021) using default settings:

```bash
uv run python scripts/production/discover_gleaner_archive_articles.py \
    --year 2021 \
    --start-month 9 \
    --end-month 11
```

### Full Year Discovery

Discover entire year using 4 parallel workers:

```bash
uv run python scripts/production/discover_gleaner_archive_articles.py \
    --year 2021 \
    --start-month 1 \
    --end-month 12 \
    --workers 4
```

### Custom Configuration

Specify custom crawl delay and output directory:

```bash
uv run python scripts/production/discover_gleaner_archive_articles.py \
    --year 2021 \
    --start-month 9 \
    --end-month 11 \
    --workers 3 \
    --crawl-delay 0.5 \
    --output-dir /path/to/output
```

## CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--year` | Yes | - | Year to discover (e.g., 2021) |
| `--start-month` | Yes | - | Starting month (1-12, inclusive) |
| `--end-month` | Yes | - | Ending month (1-12, inclusive) |
| `--workers` | No | 4 | Maximum number of parallel workers |
| `--crawl-delay` | No | 0.5 | Delay between requests in seconds |
| `--news-source-id` | No | 1 | Database ID of news source (Jamaica Gleaner) |
| `--output-dir` | No | `scripts/production/output` | Output directory path |

## Output Files

The script creates three output files:

### 1. Success File

**Format**: `gleaner_archive_{year}_{start_month}-{end_month}.jsonl`

**Example**: `gleaner_archive_2021_9-11.jsonl`

Contains successfully discovered articles in JSONL format (one JSON object per line):

```jsonl
{"url": "https://gleaner.newspaperarchive.com/kingston-gleaner/2021-09-15/", "news_source_id": 1, "section": "archive", "discovered_at": "2024-01-07T14:30:00+00:00", "title": "Kingston Gleaner September 15, 2021", "published_date": "2021-09-15T00:00:00+00:00"}
{"url": "https://gleaner.newspaperarchive.com/kingston-gleaner/2021-10-20/", "news_source_id": 1, "section": "archive", "discovered_at": "2024-01-07T14:30:05+00:00", "title": "Kingston Gleaner October 20, 2021", "published_date": "2021-10-20T00:00:00+00:00"}
```

**Fields**:
- `url`: Archive page URL
- `news_source_id`: Database ID (1 = Jamaica Gleaner)
- `section`: Always "archive" for archive discoveries
- `discovered_at`: UTC timestamp when article was discovered (ISO 8601 format)
- `title`: Page title (optional, may be `null`)
- `published_date`: Article publication date from URL (optional, may be `null`)

### 2. Failures File

**Format**: `gleaner_archive_{year}_{start_month}-{end_month}-failures.jsonl`

**Example**: `gleaner_archive_2021_9-11-failures.jsonl`

Contains stub entries for failed months (one entry per failed month):

```jsonl
{"url": "https://gleaner.newspaperarchive.com/kingston-gleaner/2021-09-01/", "news_source_id": 1, "section": "archive", "discovered_at": "2024-01-07T14:30:00+00:00", "title": "FAILED: 2021-09", "published_date": "2021-09-01T00:00:00+00:00"}
```

**Important Notes**:
- **Stub entries**: These are NOT real articles but placeholder entries indicating which months failed
- **Title format**: `FAILED: {year}-{month}` identifies failed months
- **URL pattern**: Points to first day of failed month for easy identification
- **Empty file**: If all months succeed, this file will exist but be empty (0 bytes)

### 3. Log File

**Format**: `gleaner_archive_production_{timestamp}.log`

**Example**: `gleaner_archive_production_2024-01-07_14-30-00.log`

Contains detailed logs of the discovery process, including:
- Worker start/completion messages
- Discovery statistics per month
- Error messages and stack traces for failures
- Deduplication results
- Final summary statistics

## Retry Failed Months

If some months fail during discovery, you can retry them using the failures file:

### Step 1: Identify Failed Months

Read the failures file to find failed months:

```bash
cat scripts/production/output/gleaner_archive_2021_9-11-failures.jsonl
```

Output (example):
```jsonl
{"url": "https://gleaner.newspaperarchive.com/kingston-gleaner/2021-09-01/", ..., "title": "FAILED: 2021-09", ...}
{"url": "https://gleaner.newspaperarchive.com/kingston-gleaner/2021-11-01/", ..., "title": "FAILED: 2021-11", ...}
```

This shows that months `2021-09` and `2021-11` failed.

### Step 2: Retry Failed Months

Re-run the script for only the failed months:

```bash
# Retry September 2021
uv run python scripts/production/discover_gleaner_archive_articles.py \
    --year 2021 \
    --start-month 9 \
    --end-month 9

# Retry November 2021
uv run python scripts/production/discover_gleaner_archive_articles.py \
    --year 2021 \
    --start-month 11 \
    --end-month 11
```

### Step 3: Merge Results

If you're building a comprehensive dataset, you'll need to:
1. Combine successful articles from all runs
2. Deduplicate by URL
3. Update your pipeline input

## Pipeline Integration

The JSONL output is designed for direct ingestion into your article processing pipeline:

```python
import json
from pathlib import Path

# Read discovered articles
with open('scripts/production/output/gleaner_archive_2021_9-11.jsonl') as f:
    for line in f:
        article = json.loads(line)

        # Process article through pipeline
        # Example: orchestration_service.process_article(
        #     conn=conn,
        #     url=article['url'],
        #     section=article['section'],
        #     news_source_id=article['news_source_id']
        # )
```

**Note**: The stub entries in the failures file should be filtered out before pipeline processing:

```python
# Skip stub entries (failed months)
if not article['title'].startswith('FAILED:'):
    # Process real article
    pass
```

## Performance

- **Crawl delay**: Default 0.5s between requests (respectful crawling)
- **Parallel workers**: Default 4 workers for ~4× speedup
- **Month discovery time**: ~15-16 minutes per month (30 days × 0.5s delay + network time)
- **3-month discovery**: ~15-16 minutes with 3 workers
- **12-month discovery**: ~45-48 minutes with 4 workers

## Troubleshooting

### All months failing

Check the log file for error details:
```bash
tail -n 100 scripts/production/output/gleaner_archive_production_*.log
```

Common causes:
- Network connectivity issues
- Archive website unavailable
- Rate limiting (increase `--crawl-delay`)

### Empty success file

This is normal if:
- Date range has no archive pages (e.g., future dates)
- All months failed (check failures file and logs)

### Memory usage

Large discoveries (1+ years) may use significant memory. Consider:
- Processing smaller date ranges (quarterly instead of yearly)
- Increasing crawl delay to reduce request rate

## Examples

### Quarterly Discovery

```bash
# Q1 2021
uv run python scripts/production/discover_gleaner_archive_articles.py \
    --year 2021 --start-month 1 --end-month 3 \
    --workers 3

# Q2 2021
uv run python scripts/production/discover_gleaner_archive_articles.py \
    --year 2021 --start-month 4 --end-month 6 \
    --workers 3

# Q3 2021
uv run python scripts/production/discover_gleaner_archive_articles.py \
    --year 2021 --start-month 7 --end-month 9 \
    --workers 3

# Q4 2021
uv run python scripts/production/discover_gleaner_archive_articles.py \
    --year 2021 --start-month 10 --end-month 12 \
    --workers 3
```

### Multi-Year Discovery

```bash
for year in 2019 2020 2021; do
    uv run python scripts/production/discover_gleaner_archive_articles.py \
        --year $year \
        --start-month 1 \
        --end-month 12 \
        --workers 4
done
```

## Architecture

### Workflow

1. **Argument Parsing**: Validate CLI arguments
2. **Logging Setup**: Configure file and console logging
3. **Parallel Discovery**:
   - Create tasks for each month
   - Execute with bounded concurrency (semaphore)
   - Track success/failure per month
4. **Result Separation**: Split into successful articles and failure stubs
5. **Deduplication**: Remove duplicate URLs within each group
6. **JSONL Export**: Write both success and failures files
7. **Summary**: Log statistics and file paths

### Key Functions

- `discover_month_with_tracking()`: Discovers single month with failure tracking
- `parallel_discovery_with_tracking()`: Coordinates parallel month discovery
- `write_jsonl()`: Exports DiscoveredArticle list to JSONL format

### Error Handling

- **Fail-soft**: If one month fails, others continue processing
- **Stub creation**: Failed months create placeholder entries for retry tracking
- **Logging**: All errors logged with full stack traces to log file
- **Exit codes**: Returns 0 on success, 1 on failure

## Related Scripts

- `scripts/parallel_archive_discovery.py`: Original discovery script (console output only)
- `scripts/validate_pipeline.py`: Pipeline validation script (processes single URL)

## Future Enhancements

Consider these enhancements for future versions:

1. **Batch processing script**: Read JSONL and process all articles through pipeline
2. **Progress tracking**: Track which articles were processed to avoid re-processing
3. **Resume capability**: Save checkpoint and resume from last processed month
4. **Page-level failure tracking**: Track individual archive pages (requires core code changes)
