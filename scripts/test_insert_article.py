"""Manual test script to verify insert_article query works."""
import asyncio
from datetime import datetime
import sys
from pathlib import Path

# Add project root to path so we can import modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.database import db_config
from src.db.repositories.article_repository import ArticleRepository
from src.db.models.domain import Article


async def main():
    """Test the insert_article query."""
    print("=" * 60)
    print("Testing insert_article query")
    print("=" * 60)
    print()

    # Initialize the database pool
    async with db_config:
        print("✓ Database pool initialized")
        print()

        # Create repository instance
        repo = ArticleRepository()
        print("✓ ArticleRepository created")
        print("✓ aiosql queries loaded")
        print()

        # Test data with unique URL to avoid conflicts
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        test_article = Article(
            url=f"https://jamaica-gleaner.com/test-article-{timestamp}",
            title="Test Article: Government Accountability Report",
            section="lead-stories",
            published_date=datetime(2025, 11, 15, 10, 30),
            fetched_at=datetime.now(),
            full_text="This is a test article about government accountability and transparency initiatives."
        )

        print("Inserting test article...")
        print(f"  URL: {test_article.url}")
        print(f"  Title: {test_article.title}")
        print(f"  Section: {test_article.section}")
        print()

        try:
            # Acquire connection from pool and inject it into repository
            async with db_config.connection() as conn:
                # Insert the article (now using Article model)
                result = await repo.insert_article(conn, test_article)

                print("✓ Article inserted successfully!")
                print()
                print("Returned Article model:")
                print(f"  ID: {result.id}")
                print(f"  URL: {result.url}")
                print(f"  Title: {result.title}")
                print(f"  Section: {result.section}")
                print(f"  Published Date: {result.published_date}")
                print(f"  Fetched At: {result.fetched_at}")
                print()
                print("=" * 60)
                print("✓ TEST PASSED: insert_article works with Article model!")
                print("=" * 60)

        except Exception as e:
            print(f"✗ TEST FAILED: {type(e).__name__}: {e}")
            print("=" * 60)
            raise


if __name__ == "__main__":
    asyncio.run(main())
