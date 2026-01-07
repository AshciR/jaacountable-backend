"""
Pipeline validation script with cache verification.

Processes the same article URL multiple times in a single run to demonstrate
entity normalization caching behavior. Shows cache stats and timing deltas
between runs to verify cache hits.

Usage:
    python scripts/validate_pipeline_with_caching.py <article_url> [--runs N]

Examples:
    # Default 2 runs (cache miss + cache hit)
    python scripts/validate_pipeline_with_caching.py "https://jamaica-gleaner.com/article/news/..."

    # Custom number of runs
    python scripts/validate_pipeline_with_caching.py "https://jamaica-gleaner.com/article/news/..." --runs 3

Environment Variables:
    LOG_JSON=true   Enable JSON structured logging
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.database import db_config
from config.log_config import configure_logging
from src.orchestration.service import PipelineOrchestrationService
from src.article_classification.services.in_memory_entity_cache import get_entity_cache


async def process_article_with_cache_tracking(
    url: str,
    section: str = "news",
    run_number: int = 1
) -> dict:
    """
    Process article and track cache behavior.

    Args:
        url: Article URL to process
        section: Article section (default: "news")
        run_number: Current run number (for logging)

    Returns:
        Dict with processing stats and cache deltas
    """
    logger.info(f"\n{'=' * 80}")
    logger.info(f"RUN #{run_number}: Processing article")
    logger.info(f"{'=' * 80}")

    # Initialize orchestration service (reuses singleton cache)
    service = PipelineOrchestrationService()

    # Get cache stats before processing
    cache = get_entity_cache()
    stats_before = cache.get_stats()

    logger.info(
        f"Cache BEFORE run #{run_number}: "
        f"size={stats_before['size']:,}, "
        f"hits={stats_before['hits']}, "
        f"misses={stats_before['misses']}, "
        f"hit_rate={stats_before['hit_rate']:.1%}"
    )

    # Initialize database pool
    await db_config.create_pool()

    try:
        # Process article through pipeline
        async with db_config.connection() as conn:
            result = await service.process_article(
                conn=conn,
                url=url,
                section=section,
                news_source_id=1,  # Jamaica Gleaner
                min_confidence=0.7,
            )

        # Get cache stats after processing
        stats_after = cache.get_stats()

        # Calculate deltas
        hits_delta = stats_after['hits'] - stats_before['hits']
        misses_delta = stats_after['misses'] - stats_before['misses']
        size_delta = stats_after['size'] - stats_before['size']

        logger.info(
            f"Cache AFTER run #{run_number}: "
            f"size={stats_after['size']:,} (+{size_delta}), "
            f"hits={stats_after['hits']} (+{hits_delta}), "
            f"misses={stats_after['misses']} (+{misses_delta}), "
            f"hit_rate={stats_after['hit_rate']:.1%}"
        )

        # Extract entity normalization timing from result
        entity_norm_ms = 0
        if hasattr(result, 'extra') and result.extra:
            entity_norm_ms = result.extra.get('entity_normalization_duration_ms', 0)

        cache_behavior = "CACHE HIT ✓" if hits_delta > 0 else "CACHE MISS ✗"
        logger.info(
            f"Entity normalization: {entity_norm_ms:.2f}ms ({cache_behavior})"
        )

        # Raise exception if there was an error
        if result.error:
            raise Exception(result.error)

        return {
            "run": run_number,
            "entity_norm_ms": entity_norm_ms,
            "cache_hits_delta": hits_delta,
            "cache_misses_delta": misses_delta,
            "cache_size_delta": size_delta,
            "total_cache_hits": stats_after['hits'],
            "total_cache_misses": stats_after['misses'],
            "cache_size": stats_after['size'],
            "hit_rate": stats_after['hit_rate'],
        }

    finally:
        await db_config.close_pool()


async def validate_caching(url: str, runs: int = 2) -> None:
    """
    Validate entity normalization caching by processing the same URL multiple times.

    Args:
        url: Article URL to process
        runs: Number of times to process the URL (default: 2)
    """
    logger.info(f"\n{'#' * 80}")
    logger.info(f"CACHE VALIDATION: Processing URL {runs} times")
    logger.info(f"URL: {url}")
    logger.info(f"{'#' * 80}\n")

    run_stats = []
    for i in range(1, runs + 1):
        stats = await process_article_with_cache_tracking(url, run_number=i)
        run_stats.append(stats)

    # Print summary
    logger.info(f"\n{'#' * 80}")
    logger.info("SUMMARY: Cache Performance")
    logger.info(f"{'#' * 80}\n")

    for stats in run_stats:
        speedup = ""
        if stats["run"] > 1 and run_stats[0]["entity_norm_ms"] > 0:
            speedup_factor = run_stats[0]["entity_norm_ms"] / stats["entity_norm_ms"]
            speedup = f" ({speedup_factor:.1f}x faster than run #1)"

        logger.info(
            f"Run #{stats['run']}: "
            f"entity_norm={stats['entity_norm_ms']:.2f}ms, "
            f"cache_hits_delta={stats['cache_hits_delta']}, "
            f"cache_misses_delta={stats['cache_misses_delta']}"
            f"{speedup}"
        )

    # Final cache stats
    final_stats = run_stats[-1]
    logger.info(
        f"\nFinal cache state: "
        f"size={final_stats['cache_size']}, "
        f"total_hits={final_stats['total_cache_hits']}, "
        f"total_misses={final_stats['total_cache_misses']}, "
        f"hit_rate={final_stats['hit_rate']:.1%}"
    )

    # Expected behavior validation
    logger.info(f"\n{'=' * 80}")
    logger.info("VALIDATION RESULTS:")
    logger.info(f"{'=' * 80}")

    if runs >= 2:
        first_run = run_stats[0]
        second_run = run_stats[1]

        # Run 1 should be cache miss
        if first_run["cache_misses_delta"] > 0:
            logger.info("✓ Run #1: Cache MISS (as expected - first time seeing entities)")
        else:
            logger.warning("✗ Run #1: Expected cache miss, but got hit")

        # Run 2+ should be cache hits
        if second_run["cache_hits_delta"] > 0:
            logger.info("✓ Run #2: Cache HIT (as expected - entities cached from run #1)")
        else:
            logger.warning("✗ Run #2: Expected cache hit, but got miss")

        # Check speedup
        if second_run["entity_norm_ms"] > 0 and first_run["entity_norm_ms"] > 0:
            speedup = first_run["entity_norm_ms"] / second_run["entity_norm_ms"]
            if speedup > 10:
                logger.info(f"✓ Speedup: {speedup:.1f}x faster (cache is working!)")
            else:
                logger.warning(f"✗ Speedup: Only {speedup:.1f}x (expected >10x)")

    logger.info(f"{'=' * 80}\n")


async def main() -> None:
    """Main entry point."""
    load_dotenv()

    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)

    # Configure Loguru with date+time stamped log file
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file_path = f"logs/validate_caching_{timestamp}.log"

    # Configure logging with file output
    configure_logging(
        enable_file_logging=True,
        log_file_path=log_file_path,
    )

    logger.info(f"Cache validation logging to: {log_file_path}")

    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python scripts/validate_pipeline_with_caching.py <article_url> [--runs N]")
        print("\nExamples:")
        print('  python scripts/validate_pipeline_with_caching.py "https://jamaica-gleaner.com/article/news/..."')
        print('  python scripts/validate_pipeline_with_caching.py "https://jamaica-gleaner.com/article/news/..." --runs 3')
        print("\nEnvironment Variables:")
        print("  LOG_JSON=true   Enable JSON structured logging")
        sys.exit(1)

    url = sys.argv[1]
    runs = 2  # Default

    # Parse --runs argument
    if len(sys.argv) >= 4 and sys.argv[2] == "--runs":
        try:
            runs = int(sys.argv[3])
            if runs < 1:
                print("Error: --runs must be >= 1")
                sys.exit(1)
        except ValueError:
            print("Error: --runs must be an integer")
            sys.exit(1)

    await validate_caching(url, runs)


if __name__ == "__main__":
    asyncio.run(main())
