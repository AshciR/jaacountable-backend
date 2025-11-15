"""Test script to verify connection pool health and detect leaks."""
import asyncio
from datetime import datetime
import sys
from pathlib import Path

# Add project root to path so we can import modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.database import db_config
from src.db.repositories.article_repository import ArticleRepository


def print_stats(label: str, stats: dict[str, int]) -> None:
    """Print pool statistics in a formatted way."""
    print(f"  {label}:")
    print(f"    Total connections: {stats['size']}")
    print(f"    Idle connections:  {stats['idle']}")
    print(f"    Active connections: {stats['acquired']}")
    print(f"    Min/Max size:      {stats['min_size']}/{stats['max_size']}")


async def test_single_operation():
    """Test that a single operation properly releases its connection."""
    print("\n" + "=" * 60)
    print("TEST 1: Single Operation - Connection Release")
    print("=" * 60)

    repo = ArticleRepository()

    # Check initial state
    stats_before = db_config.get_pool_stats()
    print_stats("Before operation", stats_before)

    # Perform single insert
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    async with db_config.connection() as conn:
        await repo.insert_article(
            conn,
            url=f"https://test.com/test1-{timestamp}",
            title="Test Article 1",
            section="test",
        )

        # Check stats during operation
        stats_during = db_config.get_pool_stats()
        print_stats("During operation", stats_during)

    # Check final state
    stats_after = db_config.get_pool_stats()
    print_stats("After operation", stats_after)

    # Verify no leaks
    if stats_after['acquired'] == 0:
        print("\n✓ TEST 1 PASSED: Connection properly released")
        return True
    else:
        print(f"\n✗ TEST 1 FAILED: {stats_after['acquired']} connection(s) not released!")
        return False


async def test_multiple_operations():
    """Test that multiple sequential operations don't accumulate connections."""
    print("\n" + "=" * 60)
    print("TEST 2: Multiple Sequential Operations - No Accumulation")
    print("=" * 60)

    repo = ArticleRepository()

    stats_before = db_config.get_pool_stats()
    print_stats("Before operations", stats_before)

    # Perform 5 sequential inserts
    for i in range(5):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        async with db_config.connection() as conn:
            await repo.insert_article(
                conn,
                url=f"https://test.com/test2-{i}-{timestamp}",
                title=f"Test Article 2-{i}",
                section="test",
            )

    stats_after = db_config.get_pool_stats()
    print_stats("After 5 operations", stats_after)

    # Verify no leaks
    if stats_after['acquired'] == 0:
        print("\n✓ TEST 2 PASSED: All connections properly released")
        return True
    else:
        print(f"\n✗ TEST 2 FAILED: {stats_after['acquired']} connection(s) leaked!")
        return False


async def test_exception_handling():
    """Test that connections are released even when exceptions occur."""
    print("\n" + "=" * 60)
    print("TEST 3: Exception Handling - Connection Release on Error")
    print("=" * 60)

    repo = ArticleRepository()

    stats_before = db_config.get_pool_stats()
    print_stats("Before operation", stats_before)

    # Try to insert duplicate URL (should fail with UniqueViolationError)
    duplicate_url = "https://test.com/duplicate-test"

    try:
        # First insert should succeed
        async with db_config.connection() as conn:
            await repo.insert_article(
                conn,
                url=duplicate_url,
                title="First Insert",
                section="test",
            )

        # Second insert with same URL should fail
        async with db_config.connection() as conn:
            await repo.insert_article(
                conn,
                url=duplicate_url,
                title="Duplicate Insert",
                section="test",
            )
    except Exception as e:
        print(f"  Expected error occurred: {type(e).__name__}")

    stats_after = db_config.get_pool_stats()
    print_stats("After exception", stats_after)

    # Verify no leaks despite exception
    if stats_after['acquired'] == 0:
        print("\n✓ TEST 3 PASSED: Connection released despite exception")
        return True
    else:
        print(f"\n✗ TEST 3 FAILED: {stats_after['acquired']} connection(s) not released after error!")
        return False


async def test_concurrent_operations():
    """Test that concurrent operations properly manage connections."""
    print("\n" + "=" * 60)
    print("TEST 4: Concurrent Operations - Pool Handles Multiple Requests")
    print("=" * 60)

    repo = ArticleRepository()

    stats_before = db_config.get_pool_stats()
    print_stats("Before concurrent operations", stats_before)

    # Create 10 concurrent insert tasks
    async def insert_task(task_id: int):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        async with db_config.connection() as conn:
            await repo.insert_article(
                conn,
                url=f"https://test.com/concurrent-{task_id}-{timestamp}",
                title=f"Concurrent Article {task_id}",
                section="test",
            )
            # Small delay to ensure some overlap
            await asyncio.sleep(0.01)

    # Run all tasks concurrently
    tasks = [insert_task(i) for i in range(10)]
    await asyncio.gather(*tasks)

    stats_after = db_config.get_pool_stats()
    print_stats("After concurrent operations", stats_after)

    # Verify no leaks
    if stats_after['acquired'] == 0:
        print("\n✓ TEST 4 PASSED: All concurrent connections properly released")
        return True
    else:
        print(f"\n✗ TEST 4 FAILED: {stats_after['acquired']} connection(s) leaked from concurrent ops!")
        return False


async def main():
    """Run all pool health tests."""
    print("=" * 60)
    print("CONNECTION POOL HEALTH TEST SUITE")
    print("=" * 60)

    async with db_config:
        print("\n✓ Database pool initialized")

        initial_stats = db_config.get_pool_stats()
        print_stats("\nInitial pool state", initial_stats)

        # Run all tests
        results = [
            await test_single_operation(),
            await test_multiple_operations(),
            await test_exception_handling(),
            await test_concurrent_operations()
        ]

        # Summary
        print("\n" + "=" * 60)
        print("TEST SUITE SUMMARY")
        print("=" * 60)
        passed = sum(results)
        total = len(results)
        print(f"Passed: {passed}/{total}")

        if all(results):
            print("\n✓ ALL TESTS PASSED: No connection leaks detected!")
            print("=" * 60)
        else:
            print("\n✗ SOME TESTS FAILED: Connection leaks detected!")
            print("=" * 60)
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
