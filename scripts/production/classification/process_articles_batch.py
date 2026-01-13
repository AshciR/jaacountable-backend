"""
Production batch orchestration script for processing discovered articles.

Reads article URLs from JSONL files and processes them through the full pipeline:
Extract → Classify → Store

Features:
- Resume capability (--skip-existing)
- Dry-run mode (--dry-run)
- Configurable concurrency (--concurrency)
- Real-time progress tracking with rich library
- Comprehensive error handling and reporting

Usage:
    uv run python scripts/production/process_articles_batch.py \\
        --input scripts/production/output/gleaner_archive_2021_11-11.jsonl \\
        --concurrency 4 \\
        --skip-existing

Environment Variables:
    DATABASE_URL    PostgreSQL connection string
    LOG_JSON        Enable JSON logging (default: false)
"""
import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import asyncpg
from dotenv import load_dotenv
from loguru import logger
from pydantic import ValidationError
from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich import box

# Add project root to path
# Script is at scripts/production/classification/process_articles_batch.py
# So we need to go up 3 levels to reach project root
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.database import db_config
from config.log_config import configure_logging
from src.article_discovery.models import DiscoveredArticle
from src.article_persistence.repositories.article_repository import ArticleRepository
from src.orchestration.models import OrchestrationResult
from src.orchestration.service import PipelineOrchestrationService


@dataclass
class BatchStatistics:
    """Thread-safe statistics tracker for batch processing."""

    # Counts
    total: int = 0
    processed: int = 0
    extracted: int = 0
    classified: int = 0
    relevant: int = 0
    stored: int = 0
    duplicates: int = 0
    skipped_existing: int = 0

    # Error categories
    extraction_errors: int = 0
    classification_errors: int = 0
    storage_errors: int = 0
    other_errors: int = 0

    # Performance
    start_time: float = field(default_factory=time.time)

    # Lock for concurrent updates
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def increment(self, **kwargs):
        """Thread-safe increment of statistics."""
        async with self._lock:
            for key, value in kwargs.items():
                current = getattr(self, key)
                setattr(self, key, current + value)

    def get_snapshot(self) -> dict:
        """Get current statistics snapshot (not thread-safe, call from single thread)."""
        elapsed = time.time() - self.start_time
        return {
            "total": self.total,
            "processed": self.processed,
            "extracted": self.extracted,
            "classified": self.classified,
            "relevant": self.relevant,
            "stored": self.stored,
            "duplicates": self.duplicates,
            "skipped_existing": self.skipped_existing,
            "extraction_errors": self.extraction_errors,
            "classification_errors": self.classification_errors,
            "storage_errors": self.storage_errors,
            "other_errors": self.other_errors,
            "elapsed_time": elapsed,
            "articles_per_second": self.processed / elapsed if elapsed > 0 else 0.0,
        }


def classify_error(result: OrchestrationResult) -> str:
    """
    Classify error into category for statistics tracking.

    Args:
        result: OrchestrationResult with error

    Returns:
        "extraction" | "classification" | "storage" | "other"
    """
    if not result.error:
        return "none"

    # Error during extraction
    if not result.extracted:
        return "extraction"

    # Error during classification
    if result.extracted and not result.classified:
        return "classification"

    # Error during storage
    if result.extracted and result.classified and result.relevant and not result.stored:
        return "storage"

    # Other error
    return "other"


def load_jsonl_articles(file_path: Path) -> list[DiscoveredArticle]:
    """
    Load articles from JSONL file.

    Args:
        file_path: Path to JSONL file

    Returns:
        List of DiscoveredArticle objects (validated with Pydantic)

    Raises:
        ValueError: If JSONL is malformed
        ValidationError: If article doesn't match DiscoveredArticle schema
        FileNotFoundError: If file doesn't exist
    """
    if not file_path.exists():
        raise FileNotFoundError(f"JSONL file not found: {file_path}")

    articles = []
    with open(file_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                article_dict = json.loads(line)
                article = DiscoveredArticle.model_validate(article_dict)
                articles.append(article)
            except json.JSONDecodeError as e:
                raise ValueError(f"Line {line_num}: Invalid JSON: {e}")
            except ValidationError as e:
                raise ValidationError(f"Line {line_num}: {e}")

    logger.info(f"Loaded {len(articles)} articles from {file_path}")
    return articles


async def filter_existing_urls(
    conn: asyncpg.Connection,
    articles: list[DiscoveredArticle],
    article_repo: ArticleRepository,
) -> tuple[list[DiscoveredArticle], set[str]]:
    """
    Query database for existing URLs and filter articles.

    Args:
        conn: Database connection
        articles: List of DiscoveredArticle objects
        article_repo: ArticleRepository instance

    Returns:
        - Filtered articles (URLs not in database)
        - Set of existing URLs (for logging)
    """
    # Extract all URLs from articles
    all_urls = [article.url for article in articles]

    # Batch query using repository method
    existing_urls = await article_repo.get_existing_urls(conn, all_urls)

    # Filter articles to exclude existing URLs
    filtered_articles = [
        article for article in articles if article.url not in existing_urls
    ]

    logger.info(
        f"Pre-query filter: {len(existing_urls)} already exist, "
        f"{len(filtered_articles)} to process"
    )

    return filtered_articles, existing_urls


def create_statistics_table(stats: BatchStatistics) -> Table:
    """
    Create rich table with live statistics.

    Args:
        stats: BatchStatistics instance

    Returns:
        Rich Table with current statistics
    """
    snapshot = stats.get_snapshot()

    table = Table(title="Batch Processing Statistics", box=box.ROUNDED)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    # Processing stats
    table.add_row("Total Articles", str(snapshot["total"]))
    if snapshot["total"] > 0:
        pct = snapshot["processed"] / snapshot["total"] * 100
        table.add_row("Processed", f"{snapshot['processed']} ({pct:.1f}%)")
    else:
        table.add_row("Processed", str(snapshot["processed"]))

    table.add_row("Extracted", str(snapshot["extracted"]))
    table.add_row("Classified", str(snapshot["classified"]))
    table.add_row("Relevant", str(snapshot["relevant"]))
    table.add_row("Stored", f"[green]{snapshot['stored']}[/green]")
    table.add_row("Duplicates", f"[yellow]{snapshot['duplicates']}[/yellow]")

    if snapshot["skipped_existing"] > 0:
        table.add_row("Skipped (existing)", str(snapshot["skipped_existing"]))

    # Errors
    total_errors = (
        snapshot["extraction_errors"]
        + snapshot["classification_errors"]
        + snapshot["storage_errors"]
        + snapshot["other_errors"]
    )
    if total_errors > 0:
        table.add_row("", "")  # Separator
        table.add_row("Total Errors", f"[red]{total_errors}[/red]")
        table.add_row("  - Extraction", str(snapshot["extraction_errors"]))
        table.add_row("  - Classification", str(snapshot["classification_errors"]))
        table.add_row("  - Storage", str(snapshot["storage_errors"]))
        table.add_row("  - Other", str(snapshot["other_errors"]))

    # Performance
    table.add_row("", "")  # Separator
    table.add_row("Elapsed Time", f"{snapshot['elapsed_time']:.1f}s")
    table.add_row("Articles/sec", f"{snapshot['articles_per_second']:.2f}")

    return table


async def process_articles_concurrent(
    articles: list[DiscoveredArticle],
    service: PipelineOrchestrationService,
    stats: BatchStatistics,
    max_concurrency: int = 4,
    min_confidence: float = 0.7,
    dry_run: bool = False,
) -> list[OrchestrationResult]:
    """
    Process articles with bounded concurrency.

    Args:
        articles: List of DiscoveredArticle objects to process
        service: Orchestration service instance
        stats: Statistics tracker (updated in-place)
        max_concurrency: Maximum concurrent workers
        min_confidence: Minimum confidence threshold for relevance
        dry_run: If True, use transaction rollback (no database changes)

    Returns:
        List of all OrchestrationResults (including errors)
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    console = Console()

    async def bounded_task(article: DiscoveredArticle):
        async with semaphore:
            # Acquire connection from pool (blocks if pool is exhausted)
            async with db_config.connection() as conn:
                return await process_single_article(
                    service=service,
                    conn=conn,
                    article=article,
                    stats=stats,
                    min_confidence=min_confidence,
                    dry_run=dry_run,
                )

    # Create progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:

        # Create task for overall progress
        task_id = progress.add_task(
            f"[cyan]Processing {len(articles)} articles...", total=len(articles)
        )

        # Create live table below progress bar
        with Live(
            create_statistics_table(stats), console=console, refresh_per_second=2
        ) as live:

            # Background task to update display
            async def update_display():
                while stats.processed < stats.total:
                    await asyncio.sleep(0.5)
                    progress.update(task_id, completed=stats.processed)
                    live.update(create_statistics_table(stats))

            # Start update task
            update_task = asyncio.create_task(update_display())

            # Create tasks for all articles
            tasks = [bounded_task(article) for article in articles]

            # Execute with bounded concurrency
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Cancel update task
            update_task.cancel()
            try:
                await update_task
            except asyncio.CancelledError:
                pass

            # Final update
            progress.update(task_id, completed=stats.processed)
            live.update(create_statistics_table(stats))

            # Filter out exceptions and convert to OrchestrationResult
            valid_results = [
                r for r in results if isinstance(r, OrchestrationResult)
            ]
            return valid_results


async def process_single_article(
    service: PipelineOrchestrationService,
    conn: asyncpg.Connection,
    article: DiscoveredArticle,
    stats: BatchStatistics,
    min_confidence: float,
    dry_run: bool = False,
) -> Optional[OrchestrationResult]:
    """
    Process single article with error handling.

    Args:
        service: Orchestration service instance
        conn: Database connection
        article: DiscoveredArticle to process
        stats: Statistics tracker (updated in-place)
        min_confidence: Minimum confidence threshold for relevance
        dry_run: If True, use transaction rollback (no database changes)

    Returns:
        OrchestrationResult or None on unexpected error
    """
    try:
        if dry_run:
            # Start transaction and explicitly rollback after processing
            tx = conn.transaction()
            await tx.start()
            try:
                result = await service.process_article(
                    conn=conn,
                    url=article.url,
                    section=article.section,
                    news_source_id=article.news_source_id,
                    min_confidence=min_confidence,
                )
            finally:
                await tx.rollback()  # Always rollback in dry-run mode
        else:
            # Normal processing (auto-commit)
            result = await service.process_article(
                conn=conn,
                url=article.url,
                section=article.section,
                news_source_id=article.news_source_id,
                min_confidence=min_confidence,
            )

        # Classify error if any
        if result.error:
            error_category = classify_error(result)
            await stats.increment(**{f"{error_category}_errors": 1})

        # Update statistics based on result
        await stats.increment(
            processed=1,
            extracted=1 if result.extracted else 0,
            classified=1 if result.classified else 0,
            relevant=1 if result.relevant else 0,
            stored=1 if result.stored else 0,
            duplicates=(
                1
                if (
                    result.extracted
                    and result.classified
                    and result.relevant
                    and not result.stored
                    and not result.error
                )
                else 0
            ),
        )

        return result

    except Exception as e:
        # Unexpected error not caught by orchestration service
        logger.error(
            f"Unexpected error processing {article.url}: {e}", exc_info=True
        )

        await stats.increment(processed=1, other_errors=1)

        # Return error result for logging
        return OrchestrationResult(
            url=article.url,
            section=article.section,
            extracted=False,
            classified=False,
            relevant=False,
            stored=False,
            article_id=None,
            classification_count=0,
            classification_results=[],
            error=f"Unexpected error: {e}",
        )


def generate_final_report(
    stats: BatchStatistics,
    output_dir: Path,
    timestamp: str,
    input_file: str,
    concurrency: int,
    min_confidence: float,
    skip_existing: bool,
    dry_run: bool = False,
) -> dict:
    """
    Generate JSON summary report.

    Args:
        stats: BatchStatistics instance
        output_dir: Output directory for reports
        timestamp: Timestamp string for filename
        input_file: Input JSONL file path
        concurrency: Concurrency level used
        min_confidence: Minimum confidence threshold used
        skip_existing: Whether --skip-existing was used
        dry_run: Whether --dry-run was used

    Returns:
        Report dict (also written to file)
    """
    snapshot = stats.get_snapshot()

    # Calculate rates
    total_errors = (
        snapshot["extraction_errors"]
        + snapshot["classification_errors"]
        + snapshot["storage_errors"]
        + snapshot["other_errors"]
    )

    success_count = snapshot["processed"] - total_errors
    success_rate = (
        f"{success_count / snapshot['processed'] * 100:.1f}%"
        if snapshot["processed"] > 0
        else "0.0%"
    )

    relevance_rate = (
        f"{snapshot['relevant'] / snapshot['processed'] * 100:.1f}%"
        if snapshot["processed"] > 0
        else "0.0%"
    )

    storage_rate = (
        f"{snapshot['stored'] / snapshot['processed'] * 100:.1f}%"
        if snapshot["processed"] > 0
        else "0.0%"
    )

    report = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_file": input_file,
            "dry_run": dry_run,
            "concurrency": concurrency,
            "min_confidence": min_confidence,
            "skip_existing": skip_existing,
        },
        "summary": {
            "total_articles": snapshot["total"],
            "processed": snapshot["processed"],
            "extracted": snapshot["extracted"],
            "classified": snapshot["classified"],
            "relevant": snapshot["relevant"],
            "stored": snapshot["stored"],
            "duplicates": snapshot["duplicates"],
            "skipped_existing": snapshot["skipped_existing"],
            "total_errors": total_errors,
        },
        "errors_by_category": {
            "extraction": snapshot["extraction_errors"],
            "classification": snapshot["classification_errors"],
            "storage": snapshot["storage_errors"],
            "other": snapshot["other_errors"],
        },
        "performance": {
            "elapsed_seconds": round(snapshot["elapsed_time"], 2),
            "articles_per_second": round(snapshot["articles_per_second"], 2),
        },
        "outcomes": {
            "success_rate": success_rate,
            "relevance_rate": relevance_rate,
            "storage_rate": storage_rate,
        },
    }

    # Write to file
    results_dir = output_dir / "batch_results"
    results_dir.mkdir(parents=True, exist_ok=True)

    report_file = results_dir / f"batch_{timestamp}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(f"Final report written: {report_file}")
    return report


def generate_error_report(
    results: list[OrchestrationResult],
    output_dir: Path,
    timestamp: str,
) -> None:
    """
    Generate JSONL file with all failed articles for debugging.

    Args:
        results: List of all OrchestrationResults
        output_dir: Output directory for reports
        timestamp: Timestamp string for filename
    """
    error_results = [r for r in results if r.error]

    if not error_results:
        logger.info("No errors to report")
        return

    results_dir = output_dir / "batch_results"
    results_dir.mkdir(parents=True, exist_ok=True)

    error_file = results_dir / f"batch_{timestamp}_errors.jsonl"
    with open(error_file, "w") as f:
        for result in error_results:
            error_record = {
                "url": result.url,
                "section": result.section,
                "error_category": classify_error(result),
                "error_message": result.error,
                "extracted": result.extracted,
                "classified": result.classified,
                "relevant": result.relevant,
                "stored": result.stored,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            f.write(json.dumps(error_record, ensure_ascii=False) + "\n")

    logger.info(f"Error report written: {error_file} ({len(error_results)} errors)")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Process discovered articles through orchestration pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with 20 articles
  uv run python scripts/production/process_articles_batch.py --input test_batch.jsonl

  # Production run with skip-existing
  uv run python scripts/production/process_articles_batch.py \\
      --input scripts/production/output/gleaner_archive_2021_11-11.jsonl \\
      --concurrency 4 \\
      --skip-existing

  # Dry-run to test classification
  uv run python scripts/production/process_articles_batch.py \\
      --input test_batch.jsonl \\
      --dry-run
        """,
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to JSONL file with discovered articles",
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Max concurrent article processing (default: 4, range: 1-10)",
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Pre-query DB for existing URLs and skip them",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify articles but don't store in database (transaction rollback)",
    )

    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.7,
        help="Minimum confidence threshold for relevance (default: 0.7, range: 0.0-1.0)",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("scripts/production/classification/output"),
        help="Output directory for results (default: scripts/production/classification/output)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.concurrency < 1 or args.concurrency > 10:
        parser.error("--concurrency must be between 1 and 10")

    if args.min_confidence < 0.0 or args.min_confidence > 1.0:
        parser.error("--min-confidence must be between 0.0 and 1.0")

    if not args.input.exists():
        parser.error(f"Input file does not exist: {args.input}")

    return args


async def main() -> int:
    """
    Main entry point with full lifecycle management.

    Returns:
        Exit code (0=success, 1=error)
    """
    # Load environment variables
    load_dotenv()

    # Parse CLI arguments
    args = parse_args()

    # Generate timestamp for output files
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Configure logging
    logs_dir = args.output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"batch_processing_{timestamp}.log"

    configure_logging(
        enable_file_logging=True,
        log_file_path=str(log_file),
    )

    logger.info("=" * 80)
    logger.info("BATCH PROCESSING STARTED")
    logger.info("=" * 80)
    logger.info(f"Input file: {args.input}")
    logger.info(f"Concurrency: {args.concurrency}")
    logger.info(f"Min confidence: {args.min_confidence}")
    logger.info(f"Skip existing: {args.skip_existing}")
    logger.info(f"Dry-run mode: {args.dry_run}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Log file: {log_file}")
    logger.info("=" * 80)

    try:
        # Load JSONL articles
        logger.info("Loading articles from JSONL...")
        articles = load_jsonl_articles(args.input)

        # Initialize database pool
        logger.info("Initializing database connection pool...")
        await db_config.create_pool(
            min_size=args.concurrency,
            max_size=args.concurrency * 2,
            command_timeout=60.0,
        )

        # Initialize statistics
        stats = BatchStatistics()
        stats.total = len(articles)

        try:
            # Initialize repositories and services
            article_repo = ArticleRepository()

            # Use orchestration service as context manager for HTTP connection pooling
            async with PipelineOrchestrationService() as service:
                # Optional: Pre-query existing URLs (--skip-existing)
                if args.skip_existing:
                    logger.info("Filtering existing URLs...")
                    # Use context manager to close db connections. We reuse connection from the pool
                    async with db_config.connection() as conn:
                        articles, existing_urls = await filter_existing_urls(
                            conn, articles, article_repo
                        )
                        stats.skipped_existing = len(existing_urls)
                        stats.total = len(articles)

                if len(articles) == 0:
                    logger.warning("No articles to process (all skipped or empty input)")
                    return 0

                # Run concurrent processing with progress display
                logger.info(
                    f"Processing {len(articles)} articles with {args.concurrency} workers..."
                )
                results = await process_articles_concurrent(
                    articles=articles,
                    service=service,
                    stats=stats,
                    max_concurrency=args.concurrency,
                    min_confidence=args.min_confidence,
                    dry_run=args.dry_run,
                )

                # Generate final reports
                logger.info("Generating reports...")
                report = generate_final_report(
                    stats=stats,
                    output_dir=args.output_dir,
                    timestamp=timestamp,
                    input_file=str(args.input),
                    concurrency=args.concurrency,
                    min_confidence=args.min_confidence,
                    skip_existing=args.skip_existing,
                    dry_run=args.dry_run,
                )

                generate_error_report(
                    results=results,
                    output_dir=args.output_dir,
                    timestamp=timestamp,
                )

                # Console output
                console = Console()
                console.print()
                console.print("=" * 80, style="bold green")
                console.print(
                    "BATCH PROCESSING COMPLETED SUCCESSFULLY", style="bold green"
                )
                console.print("=" * 80, style="bold green")
                console.print()
                console.print(
                    f"  Summary: {args.output_dir}/batch_results/batch_{timestamp}.json"
                )
                console.print(
                    f"  Errors:  {args.output_dir}/batch_results/batch_{timestamp}_errors.jsonl"
                )
                console.print(f"  Logs:    {log_file}")
                console.print()

                logger.info("=" * 80)
                logger.info("BATCH PROCESSING COMPLETED")
                logger.info(f"Processed: {stats.processed}")
                logger.info(f"Stored: {stats.stored}")
                logger.info(
                    f"Errors: {stats.extraction_errors + stats.classification_errors + stats.storage_errors + stats.other_errors}"
                )
                logger.info("=" * 80)

                return 0

        finally:
            # Close database pool
            logger.info("Closing database connection pool...")
            await db_config.close_pool()

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
