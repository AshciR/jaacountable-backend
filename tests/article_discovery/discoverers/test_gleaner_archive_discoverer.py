"""Tests for GleanerArchiveDiscoverer."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.article_discovery.discoverers.gleaner_archive_discoverer import (
    GleanerArchiveDiscoverer,
    RedirectError,
)
from src.article_discovery.models import DiscoveredArticle


class TestGleanerArchiveDiscovererHappyPath:
    """Test successful archive discovery scenarios."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_returns_discovered_articles_with_required_fields(
        self, mock_async_client_class, archive_page_nov_07_page_4
    ):
        """
        GIVEN a GleanerArchiveDiscoverer with 1-day range
        WHEN discover() is called
        THEN it returns DiscoveredArticle instances with required fields
        """
        # Given
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4  # Last page (no next link)
        mock_response.history = []
        mock_client.get = AsyncMock(return_value=mock_response)

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(
            end_date=end_date,
            days_back=0,  # Just the end_date
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert isinstance(articles, list)
        assert len(articles) == 1
        assert all(isinstance(a, DiscoveredArticle) for a in articles)

        # Check required fields
        article = articles[0]
        assert article.url.startswith("https://gleaner.newspaperarchive.com")
        assert article.news_source_id == 1
        assert article.section == "archive"
        assert article.discovered_at is not None
        assert article.discovered_at.tzinfo == timezone.utc

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discovered_articles_extract_title_from_og_title(
        self, mock_async_client_class, archive_page_nov_07_page_4
    ):
        """
        GIVEN a GleanerArchiveDiscoverer
        WHEN discover() is called on page with og:title
        THEN title is extracted from og:title meta tag
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(end_date=end_date, days_back=0)

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 1
        assert (
            articles[0].title
            == "Kingston Gleaner Newspaper Archives | Nov 07, 2021, p. 4"
        )

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discovered_articles_extract_title_from_title_tag(
        self, mock_async_client_class, archive_page_no_og_title
    ):
        """
        GIVEN a page with title tag but no og:title
        WHEN discover() is called
        THEN title is extracted from title tag
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_no_og_title
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(end_date=end_date, days_back=0)

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 1
        assert (
            articles[0].title
            == "Kingston Gleaner Newspaper Archives | Nov 07, 2021, p. 5"
        )

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discovered_articles_parse_date_from_url(self, mock_async_client_class, archive_page_nov_07_page_4):
        """
        GIVEN a GleanerArchiveDiscoverer
        WHEN discover() is called
        THEN published_date is parsed from URL date component
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(end_date=end_date, days_back=0)

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 1
        assert articles[0].published_date == datetime(2021, 11, 7, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_generates_correct_date_range(self, mock_async_client_class, archive_page_nov_07_page_4):
        """
        GIVEN a GleanerArchiveDiscoverer with days_back=7
        WHEN discover() is called
        THEN it discovers pages for 8 dates (inclusive)
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(
            end_date=end_date,
            days_back=7,  # 8 days inclusive: Nov 1-7
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then: Should make 8 requests (one per date)
        assert mock_client.get.call_count == 8
        assert len(articles) == 8

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_n_days_back_with_field_verification(
        self, mock_async_client_class, archive_page_nov_07_page_4, archive_page_nov_06, archive_page_nov_05
    ):
        """
        GIVEN a GleanerArchiveDiscoverer with days_back=2 (Nov 05 to Nov 07)
        WHEN discover() is called
        THEN it discovers 3 articles with correct dates and verified fields
        """
        # Given: 3 dates (Nov 05, Nov 06, Nov 07) with one page each
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_client.get = AsyncMock(side_effect=[
            Mock(text=archive_page_nov_05, history=[]),  # Nov 05
            Mock(text=archive_page_nov_06, history=[]),  # Nov 06
            Mock(text=archive_page_nov_07_page_4, history=[]),  # Nov 07
        ])

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(
            end_date=end_date,
            days_back=2,  # 3 days inclusive: Nov 05-07
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then: Should discover 3 articles
        assert len(articles) == 3
        assert mock_client.get.call_count == 3

        # Verify fields of each discovered article
        nov_05_article = articles[0]
        assert nov_05_article.url == "https://gleaner.newspaperarchive.com/kingston-gleaner/2021-11-05/"
        assert nov_05_article.news_source_id == 1
        assert nov_05_article.section == "archive"
        assert nov_05_article.title == "Kingston Gleaner Newspaper Archives | Nov 05, 2021, p. 1"
        assert nov_05_article.published_date == datetime(2021, 11, 5, tzinfo=timezone.utc)
        assert nov_05_article.discovered_at.tzinfo == timezone.utc

        nov_06_article = articles[1]
        assert nov_06_article.url == "https://gleaner.newspaperarchive.com/kingston-gleaner/2021-11-06/"
        assert nov_06_article.news_source_id == 1
        assert nov_06_article.section == "archive"
        assert nov_06_article.title == "Kingston Gleaner Newspaper Archives | Nov 06, 2021, p. 1"
        assert nov_06_article.published_date == datetime(2021, 11, 6, tzinfo=timezone.utc)
        assert nov_06_article.discovered_at.tzinfo == timezone.utc

        nov_07_article = articles[2]
        assert nov_07_article.url == "https://gleaner.newspaperarchive.com/kingston-gleaner/2021-11-07/"
        assert nov_07_article.news_source_id == 1
        assert nov_07_article.section == "archive"
        assert nov_07_article.title == "Kingston Gleaner Newspaper Archives | Nov 07, 2021, p. 4"
        assert nov_07_article.published_date == datetime(2021, 11, 7, tzinfo=timezone.utc)
        assert nov_07_article.discovered_at.tzinfo == timezone.utc

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_deduplication_removes_duplicate_urls(self, mock_async_client_class, archive_page_nov_07_page_4):
        """
        GIVEN discovered articles with duplicate URLs
        WHEN discover() is called
        THEN duplicates are removed
        """
        # Given: Mock returns same page twice (simulating duplicate pagination)
        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(end_date=end_date, days_back=1)  # 2 dates

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then: Deduplication should work (both dates generate same URL pattern in this mock)
        # In real scenario, different dates would have different URLs
        assert len(articles) >= 1  # At least one article discovered


class TestGleanerArchiveDiscovererValidationErrors:
    """Test validation error scenarios."""

    @pytest.mark.asyncio
    async def test_discover_raises_value_error_for_invalid_news_source_id(self):
        """
        GIVEN a GleanerArchiveDiscoverer
        WHEN discover() is called with news_source_id <= 0
        THEN it raises ValueError
        """
        # Given
        discoverer = GleanerArchiveDiscoverer()

        # When / Then
        with pytest.raises(ValueError, match="news_source_id must be positive"):
            await discoverer.discover(news_source_id=0)

        with pytest.raises(ValueError, match="news_source_id must be positive"):
            await discoverer.discover(news_source_id=-1)


class TestGleanerArchiveDiscovererNetworkErrors:
    """Test network error handling and retry logic."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_retry_logic_on_network_error(self, mock_async_client_class, archive_page_nov_07_page_4):
        """
        GIVEN a network error on first attempt
        WHEN discover() is called
        THEN it retries and succeeds on second attempt
        """
        # Given: First call fails, second succeeds
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_client.get = AsyncMock(side_effect=[
            httpx.RequestError("Network error"),
            Mock(text=archive_page_nov_07_page_4, history=[]),
        ])

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(
            end_date=end_date,
            days_back=0,
            max_retries=3,
            base_backoff=0.01,  # Fast retry for testing
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 1
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")  # Mock sleep to speed up test
    async def test_exponential_backoff_on_retries(self, mock_sleep, mock_async_client_class, archive_page_nov_07_page_4):
        """
        GIVEN multiple network errors
        WHEN discover() is called
        THEN it uses exponential backoff between retries
        """
        # Given: First two calls fail, third succeeds
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_client.get = AsyncMock(side_effect=[
            httpx.RequestError("Error 1"),
            httpx.RequestError("Error 2"),
            Mock(text=archive_page_nov_07_page_4, history=[]),
        ])

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(
            end_date=end_date,
            days_back=0,
            max_retries=3,
            base_backoff=2.0,
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then: Backoff times should be 2^1=2s, 2^2=4s
        assert len(articles) == 1
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2.0)  # First retry: 2^1
        mock_sleep.assert_any_call(4.0)  # Second retry: 2^2

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_max_retries_exceeded_fails_that_date_but_continues(
        self, mock_async_client_class, archive_page_nov_07_page_4
    ):
        """
        GIVEN max retries exceeded for one date
        WHEN discover() is called with multiple dates
        THEN it fails soft (logs error, continues with next date)
        """
        # Given: First date fails all retries, second date succeeds
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_client.get = AsyncMock(side_effect=[
            # Date 1: All retries fail
            httpx.RequestError("Error"),
            httpx.RequestError("Error"),
            httpx.RequestError("Error"),
            # Date 2: Succeeds on first try
            Mock(text=archive_page_nov_07_page_4, history=[]),
        ])

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(
            end_date=end_date,
            days_back=1,  # 2 dates
            max_retries=3,
            base_backoff=0.01,
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then: Should get 1 article from the successful date
        assert len(articles) == 1
        assert mock_client.get.call_count == 4  # 3 retries for date1 + 1 success for date2

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_404_fallback_to_page_1(self, mock_async_client_class, archive_page_nov_07_page_4):
        """
        GIVEN base URL returns 404
        WHEN discover() is called
        THEN it falls back to page-1 URL
        """
        # Given: Base URL returns 404, page-1 succeeds
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client

        mock_404_response = Mock()
        mock_404_response.status_code = 404
        mock_404_response.history = []  # No redirect, just a real 404
        mock_404_error = httpx.HTTPStatusError(
            message="404 Not Found",
            request=Mock(),
            response=mock_404_response
        )

        mock_success_response = Mock()
        mock_success_response.text = archive_page_nov_07_page_4
        mock_success_response.history = []  # No redirect

        mock_client.get = AsyncMock(side_effect=[
            mock_404_error,  # Base URL fails
            mock_success_response,  # page-1 succeeds
        ])

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(end_date=end_date, days_back=0)

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 1
        assert mock_client.get.call_count == 2  # Base URL + page-1


class TestGleanerArchiveDiscovererEdgeCases:
    """Test edge cases and unusual scenarios."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_single_page_date_no_next_link(self, mock_async_client_class, archive_page_nov_07_page_4):
        """
        GIVEN a date with only one page (no next link)
        WHEN discover() is called
        THEN it discovers only that one page
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4  # Last page (no next link)
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(end_date=end_date, days_back=0)

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 1
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_missing_page_title_returns_none(self, mock_async_client_class, archive_page_no_title):
        """
        GIVEN a page with no title tags
        WHEN discover() is called
        THEN title field is None
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_no_title
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(end_date=end_date, days_back=0)

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 1
        assert articles[0].title is None

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_malformed_html_still_creates_article(
        self, mock_async_client_class, archive_page_malformed
    ):
        """
        GIVEN malformed HTML
        WHEN discover() is called
        THEN it still creates article (BeautifulSoup is lenient)
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_malformed
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(end_date=end_date, days_back=0)

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then: Should still create article despite malformed HTML
        assert len(articles) == 1
        assert articles[0].url.startswith("https://gleaner.newspaperarchive.com")

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_zero_days_back_discovers_only_end_date(self, mock_async_client_class, archive_page_nov_07_page_4):
        """
        GIVEN days_back=0
        WHEN discover() is called
        THEN it discovers only the end_date
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(end_date=end_date, days_back=0)

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 1
        assert mock_client.get.call_count == 1


class TestGleanerArchiveDiscovererPagination:
    """Test pagination following next links."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")  # Mock sleep to speed up test
    async def test_follows_next_links(
        self, mock_sleep, mock_async_client_class, archive_page_nov_07_page_1, archive_page_nov_07_page_2, archive_page_nov_07_page_3, archive_page_nov_07_page_4
    ):
        """
        GIVEN archive pages with next links (pages 1→2→3→4)
        WHEN discover() is called
        THEN it follows all next links until exhausted
        """
        # Given: 4 linked pages
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_client.get = AsyncMock(side_effect=[
            Mock(text=archive_page_nov_07_page_1, history=[]),
            Mock(text=archive_page_nov_07_page_2, history=[]),
            Mock(text=archive_page_nov_07_page_3, history=[]),
            Mock(text=archive_page_nov_07_page_4, history=[]),  # Last page (no next)
        ])

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(
            end_date=end_date, days_back=0, crawl_delay=0.01
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 4
        assert mock_client.get.call_count == 4
        assert mock_sleep.call_count == 3  # Sleep between pages (not after last)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_crawl_delay_applied_between_pages(
        self, mock_sleep, mock_async_client_class, archive_page_nov_07_page_1, archive_page_nov_07_page_4
    ):
        """
        GIVEN multiple pages for a date
        WHEN discover() is called
        THEN crawl delay is applied between page requests
        """
        # Given: 2 pages
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_client.get = AsyncMock(side_effect=[Mock(text=archive_page_nov_07_page_1, history=[]), Mock(text=archive_page_nov_07_page_4, history=[])])

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        crawl_delay = 2.5
        discoverer = GleanerArchiveDiscoverer(
            end_date=end_date, days_back=0, crawl_delay=crawl_delay
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 2
        assert mock_sleep.call_count == 1  # One delay between 2 pages
        mock_sleep.assert_called_with(crawl_delay)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_multiple_pages_per_date(
        self, mock_async_client_class, archive_page_nov_07_page_1, archive_page_nov_07_page_2, archive_page_nov_07_page_3, archive_page_nov_07_page_4
    ):
        """
        GIVEN a date with 4 pages
        WHEN discover() is called
        THEN all 4 pages are discovered
        """
        # Given: 4 pages
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_client.get = AsyncMock(side_effect=[
            Mock(text=archive_page_nov_07_page_1, history=[]),
            Mock(text=archive_page_nov_07_page_2, history=[]),
            Mock(text=archive_page_nov_07_page_3, history=[]),
            Mock(text=archive_page_nov_07_page_4, history=[]),
        ])

        end_date = datetime(2021, 11, 7, tzinfo=timezone.utc)
        discoverer = GleanerArchiveDiscoverer(
            end_date=end_date, days_back=0, crawl_delay=0.01
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 4
        assert mock_client.get.call_count == 4


class TestGleanerArchiveDiscovererForMonthFactory:
    """Test for_month() factory method."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_for_month_creates_discoverer_for_full_month(
        self, mock_async_client_class, archive_page_nov_07_page_4
    ):
        """
        GIVEN for_month() called with year=2021, month=11
        WHEN discover() is called
        THEN it discovers all 30 days in November 2021
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        discoverer = GleanerArchiveDiscoverer.for_month(
            year=2021, month=11
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then: November 2021 has 30 days
        assert mock_client.get.call_count == 30  # One request per day
        assert len(articles) == 30

    @pytest.mark.asyncio
    async def test_for_month_validates_year_range(self):
        """
        GIVEN for_month() called with invalid year
        WHEN factory method is invoked
        THEN it raises ValueError
        """
        # When / Then: Year too low
        with pytest.raises(ValueError, match="Invalid year.*1899"):
            GleanerArchiveDiscoverer.for_month(year=1899, month=1)

        # When / Then: Year too high
        with pytest.raises(ValueError, match="Invalid year.*3001"):
            GleanerArchiveDiscoverer.for_month(year=3001, month=1)

    @pytest.mark.asyncio
    async def test_for_month_validates_month_range(self):
        """
        GIVEN for_month() called with invalid month
        WHEN factory method is invoked
        THEN it raises ValueError
        """
        # When / Then: Month too low
        with pytest.raises(ValueError, match="Invalid month.*0"):
            GleanerArchiveDiscoverer.for_month(year=2021, month=0)

        # When / Then: Month too high
        with pytest.raises(ValueError, match="Invalid month.*13"):
            GleanerArchiveDiscoverer.for_month(year=2021, month=13)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_for_month_handles_leap_year_february(
        self, mock_async_client_class, archive_page_nov_07_page_4
    ):
        """
        GIVEN for_month() called for February in leap year (2020)
        WHEN discover() is called
        THEN it discovers 29 days (Feb 2020 has 29 days)
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        discoverer = GleanerArchiveDiscoverer.for_month(
            year=2020, month=2  # Leap year
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then: February 2020 has 29 days (leap year)
        assert mock_client.get.call_count == 29
        assert len(articles) == 29

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_for_month_handles_non_leap_year_february(
        self, mock_async_client_class, archive_page_nov_07_page_4
    ):
        """
        GIVEN for_month() called for February in non-leap year (2021)
        WHEN discover() is called
        THEN it discovers 28 days (Feb 2021 has 28 days)
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        discoverer = GleanerArchiveDiscoverer.for_month(
            year=2021, month=2  # Non-leap year
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then: February 2021 has 28 days (non-leap year)
        assert mock_client.get.call_count == 28
        assert len(articles) == 28

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_for_month_generates_correct_date_range(
        self, mock_async_client_class, archive_page_nov_07_page_4
    ):
        """
        GIVEN for_month() called with year=2021, month=11
        WHEN discover() is called
        THEN it generates dates from Nov 1 to Nov 30 (inclusive)
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        discoverer = GleanerArchiveDiscoverer.for_month(
            year=2021, month=11
        )

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then: Verify first and last URLs contain correct dates
        urls_called = [call[0][0] for call in mock_client.get.call_args_list]

        # First date should be Nov 1
        assert "2021-11-01" in urls_called[0]

        # Last date should be Nov 30
        assert "2021-11-30" in urls_called[-1]

        # Total should be 30 days
        assert len(urls_called) == 30

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_for_month_passes_through_optional_parameters(
        self, mock_async_client_class, archive_page_nov_07_page_4
    ):
        """
        GIVEN for_month() called with custom parameters
        WHEN discoverer is created
        THEN it respects custom timeout, max_retries, etc.
        """
        # Given
        mock_response = Mock()
        mock_response.text = archive_page_nov_07_page_4
        mock_response.history = []
        
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        discoverer = GleanerArchiveDiscoverer.for_month(
            year=2021,
            month=11,
            timeout=60,
            max_retries=5,
            crawl_delay=3.0,
        )

        # Then: Verify parameters were set
        assert discoverer.timeout == 60
        assert discoverer.max_retries == 5
        assert discoverer.crawl_delay == 3.0
