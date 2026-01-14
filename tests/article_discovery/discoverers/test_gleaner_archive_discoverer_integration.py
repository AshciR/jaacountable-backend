"""Integration tests for GleanerArchiveDiscoverer with real HTTP requests."""

import logging
import re
from datetime import datetime, timezone

import pytest

from src.article_discovery.discoverers.gleaner_archive_discoverer import (
    GleanerArchiveDiscoverer,
)
from src.article_discovery.models import DiscoveredArticle

logger = logging.getLogger(__name__)


@pytest.mark.external
@pytest.mark.integration
class TestGleanerArchiveDiscovererIntegration:
    """Integration tests with real HTTP requests (marked for CI/CD)."""

    @pytest.mark.asyncio
    async def test_discover_real_archive_pages_for_two_days(self):
        """
        Integration test: Discover real archive pages for 2 days.

        GIVEN a GleanerArchiveDiscoverer configured for 2 days (Nov 06-07, 2021)
        WHEN discover() is called
        THEN it should return discovered articles from real archive pages
        """
        # Given
        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(
            end_date=end_date,
            days_back=1,  # 2 days: Nov 06-07
            crawl_delay=0.5,  # Respectful crawling
        )

        # When
        articles: list[DiscoveredArticle] = await discoverer.discover(news_source_id=1)

        # Then: Assert exact count (40 total: 20 pages per date for 2 dates)
        assert len(articles) == 40, f"Expected 40 articles, got {len(articles)}"

        assert all(isinstance(a, DiscoveredArticle) for a in articles)
        assert all(a.section == "archive" for a in articles)
        assert all(
            a.url.startswith("https://gleaner.newspaperarchive.com") for a in articles
        )
        assert all(a.published_date is not None for a in articles)

        # Assert all titles match expected pattern for Nov 06 and Nov 07
        _assert_titles_match_pattern(articles, date_pattern="(06|07)")

        # Verify we have 20 articles for each date
        nov_06_articles = _assert_articles_for_date(
            articles, datetime(2021, 11, 6, tzinfo=timezone.utc), expected_count=20
        )
        nov_07_articles = _assert_articles_for_date(
            articles, datetime(2021, 11, 7, tzinfo=timezone.utc), expected_count=20
        )

        # Log results for debugging
        logger.info(f"Discovered {len(articles)} articles")
        logger.info(f"  Nov 06: {len(nov_06_articles)} articles")
        logger.info(f"  Nov 07: {len(nov_07_articles)} articles")
        for article in articles[:3]:
            logger.info(f"  {article.url} - {article.title}")

def _assert_titles_match_pattern(articles: list[DiscoveredArticle], date_pattern: str) -> None:
    """
    Assert all article titles match expected pattern.

    Args:
        articles: List of discovered articles
        date_pattern: Regex pattern for dates (e.g., "(06|07)" for Nov 06 and Nov 07)
    """
    for article in articles:
        # Titles should match: "Kingston Gleaner Newspaper Archives | Nov DD, 2021, p. N"
        assert article.title is not None, f"Article {article.url} has no title"
        pattern = rf"Kingston Gleaner Newspaper Archives \| Nov {date_pattern}, 2021, p\. \d+"
        assert re.match(
            pattern, article.title
        ), f"Title doesn't match pattern: {article.title}"


def _assert_articles_for_date(
    articles: list[DiscoveredArticle],
    date: datetime,
    expected_count: int,
) -> list[DiscoveredArticle]:
    """
    Assert expected number of articles for a specific date.

    Args:
        articles: List of all discovered articles
        date: The date to filter by
        expected_count: Expected number of articles for this date

    Returns:
        List of articles for the specified date
    """
    date_articles = [a for a in articles if a.published_date == date]

    assert (
        len(date_articles) == expected_count
    ), f"Expected {expected_count} articles for {date.date()}, got {len(date_articles)}"

    return date_articles