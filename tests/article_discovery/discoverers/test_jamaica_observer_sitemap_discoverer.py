"""Tests for JamaicaObserverSitemapDiscoverer."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.article_discovery.discoverers.jamaica_observer_sitemap_discoverer import (
    JamaicaObserverSitemapDiscoverer,
)
from src.article_discovery.models import DiscoveredArticle

# Shared date range: June 2020 (used across most tests)
_START = datetime(2020, 6, 1, tzinfo=timezone.utc)
_END = datetime(2020, 6, 30, tzinfo=timezone.utc)


def _make_response(xml: str) -> Mock:
    """Build a mock httpx.Response with the given XML body."""
    resp = Mock()
    resp.text = xml
    resp.raise_for_status = Mock()  # no-op — does not raise
    return resp


def _make_discoverer(**kwargs) -> JamaicaObserverSitemapDiscoverer:
    """Build a discoverer for June 2020 with fast settings for testing."""
    defaults = dict(
        start_date=_START,
        end_date=_END,
        base_backoff=0.01,
        crawl_delay=0.01,
    )
    defaults.update(kwargs)
    return JamaicaObserverSitemapDiscoverer(**defaults)


class TestJamaicaObserverSitemapDiscovererHappyPath:
    """Test successful sitemap discovery scenarios."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_returns_discovered_articles(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN a discoverer configured for June 2020
        WHEN discover() is called with valid index and in-range sitemap
        THEN it returns a list of DiscoveredArticle instances
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),         # sitemap index
            _make_response(jo_post_sitemap_in_range), # post-sitemap320
            _make_response(jo_post_sitemap_in_range), # post-sitemap321
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then
        assert isinstance(articles, list)
        assert len(articles) > 0
        assert all(isinstance(a, DiscoveredArticle) for a in articles)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discovered_articles_have_correct_fields(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN a valid post-sitemap with 3 in-range articles
        WHEN discover() is called
        THEN each article has correct url, news_source_id=2, section='archive',
             title=slug, published_date from URL, and timezone-aware discovered_at
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),
            _make_response(jo_post_sitemap_in_range),
            _make_response(jo_post_sitemap_in_range),
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then — verify fields on the June 15 article
        article = next(
            a for a in articles
            if a.url == "https://www.jamaicaobserver.com/2020/06/15/article-one-slug/"
        )
        assert article.url == "https://www.jamaicaobserver.com/2020/06/15/article-one-slug/"
        assert article.news_source_id == 2
        assert article.section == "archive"
        assert article.title == "article-one-slug"
        assert article.published_date == datetime(2020, 6, 15, tzinfo=timezone.utc)
        assert article.discovered_at.tzinfo == timezone.utc

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_filters_articles_outside_date_range(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_mixed
    ):
        """
        GIVEN a sitemap with URLs before, inside, and after the target range
        WHEN discover() is called
        THEN only the 2 in-range URLs are returned (May 31 and July 1 excluded)
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),
            _make_response(jo_post_sitemap_mixed),
            _make_response(jo_post_sitemap_mixed),
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then
        urls = {a.url for a in articles}
        assert "https://www.jamaicaobserver.com/2020/06/20/first-in-range-slug/" in urls
        assert "https://www.jamaicaobserver.com/2020/06/21/second-in-range-slug/" in urls
        assert "https://www.jamaicaobserver.com/2020/05/31/before-start-slug/" not in urls
        assert "https://www.jamaicaobserver.com/2020/07/01/after-end-slug/" not in urls

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_deduplicates_articles_across_sitemaps(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN two sitemaps that both contain the same URLs
        WHEN discover() is called
        THEN duplicate URLs are removed, keeping first occurrence
        """
        # Given: both sitemaps return the same 3 articles
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),
            _make_response(jo_post_sitemap_in_range),  # 3 articles
            _make_response(jo_post_sitemap_in_range),  # same 3 articles again
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then: 3 unique articles, not 6
        assert len(articles) == 3

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_processes_all_relevant_sitemaps(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN a sitemap index with 2 in-range post-sitemaps
        WHEN discover() is called
        THEN it fetches the index plus both post-sitemaps (3 total requests)
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),
            _make_response(jo_post_sitemap_in_range),
            _make_response(jo_post_sitemap_in_range),
        ])

        discoverer = _make_discoverer()

        # When
        await discoverer.discover(news_source_id=2)

        # Then: index + 2 post-sitemaps = 3 total HTTP requests
        assert mock_client.get.call_count == 3


class TestJamaicaObserverSitemapDiscovererValidation:
    """Test constructor and input validation errors."""

    @pytest.mark.asyncio
    async def test_discover_raises_value_error_for_zero_news_source_id(self):
        """
        GIVEN a discoverer
        WHEN discover() is called with news_source_id=0
        THEN it raises ValueError
        """
        discoverer = _make_discoverer()
        with pytest.raises(ValueError, match="news_source_id must be positive"):
            await discoverer.discover(news_source_id=0)

    @pytest.mark.asyncio
    async def test_discover_raises_value_error_for_negative_news_source_id(self):
        """
        GIVEN a discoverer
        WHEN discover() is called with news_source_id=-1
        THEN it raises ValueError
        """
        discoverer = _make_discoverer()
        with pytest.raises(ValueError, match="news_source_id must be positive"):
            await discoverer.discover(news_source_id=-1)

    def test_init_raises_for_naive_start_date(self):
        """
        GIVEN a naive (timezone-unaware) start_date
        WHEN discoverer is initialized
        THEN it raises ValueError
        """
        with pytest.raises(ValueError, match="start_date must be timezone-aware"):
            JamaicaObserverSitemapDiscoverer(
                start_date=datetime(2020, 6, 1),  # no tzinfo
                end_date=_END,
            )

    def test_init_raises_for_naive_end_date(self):
        """
        GIVEN a naive (timezone-unaware) end_date
        WHEN discoverer is initialized
        THEN it raises ValueError
        """
        with pytest.raises(ValueError, match="end_date must be timezone-aware"):
            JamaicaObserverSitemapDiscoverer(
                start_date=_START,
                end_date=datetime(2020, 6, 30),  # no tzinfo
            )

    def test_init_raises_when_start_date_after_end_date(self):
        """
        GIVEN start_date after end_date
        WHEN discoverer is initialized
        THEN it raises ValueError
        """
        with pytest.raises(ValueError, match="start_date must be <= end_date"):
            JamaicaObserverSitemapDiscoverer(
                start_date=datetime(2020, 6, 30, tzinfo=timezone.utc),
                end_date=datetime(2020, 6, 1, tzinfo=timezone.utc),
            )


class TestJamaicaObserverSitemapDiscovererNetworkErrors:
    """Test retry logic and failure handling."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_retry_on_network_error_succeeds_on_second_attempt(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN a transient network error on the first attempt
        WHEN discover() is called
        THEN it retries and succeeds on the second attempt
        """
        # Given: first get call raises, subsequent calls succeed
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            httpx.RequestError("Connection reset"),          # index: attempt 1 fails
            _make_response(jo_sitemap_index),                # index: attempt 2 succeeds
            _make_response(jo_post_sitemap_in_range),        # post-sitemap320
            _make_response(jo_post_sitemap_in_range),        # post-sitemap321
        ])

        discoverer = _make_discoverer(max_retries=3)

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then: succeeds despite initial failure
        assert len(articles) > 0
        assert mock_client.get.call_count == 4  # 2 for index + 2 for sitemaps

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_exponential_backoff_on_retries(
        self, mock_sleep, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN two consecutive network errors before success
        WHEN discover() is called
        THEN it sleeps for 2^1=2s and 2^2=4s between retries
        """
        # Given: two failures then success on the index fetch
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            httpx.RequestError("Error 1"),               # index attempt 1
            httpx.RequestError("Error 2"),               # index attempt 2
            _make_response(jo_sitemap_index),            # index attempt 3 succeeds
            _make_response(jo_post_sitemap_in_range),    # post-sitemap320
            _make_response(jo_post_sitemap_in_range),    # post-sitemap321
        ])

        discoverer = _make_discoverer(max_retries=3, base_backoff=2.0)

        # When
        await discoverer.discover(news_source_id=2)

        # Then: backoff sleeps at 2^1=2s and 2^2=4s
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        assert 2.0 in sleep_calls  # first retry backoff
        assert 4.0 in sleep_calls  # second retry backoff

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_failed_sitemap_tracked_in_failed_sitemaps_attribute(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN a post-sitemap that fails all retry attempts
        WHEN discover() is called
        THEN the sitemap filename is recorded in discoverer.failed_sitemaps
        """
        # Given: index succeeds, post-sitemap320 fails all retries, post-sitemap321 succeeds
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),
            httpx.RequestError("Error"),               # post-sitemap320: attempt 1
            httpx.RequestError("Error"),               # post-sitemap320: attempt 2
            httpx.RequestError("Error"),               # post-sitemap320: attempt 3
            _make_response(jo_post_sitemap_in_range),  # post-sitemap321 succeeds
        ])

        discoverer = _make_discoverer(max_retries=3)

        # When
        await discoverer.discover(news_source_id=2)

        # Then: failed sitemap is tracked
        assert len(discoverer.failed_sitemaps) == 1
        assert "post-sitemap320.xml" in discoverer.failed_sitemaps[0]

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_failed_sitemap_fail_soft_continues_other_sitemaps(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN one post-sitemap fails all retries
        WHEN discover() is called
        THEN the remaining sitemaps are still processed (fail-soft)
        """
        # Given: post-sitemap320 fails, post-sitemap321 succeeds (3 articles)
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),
            httpx.RequestError("Error"),               # post-sitemap320: attempt 1
            httpx.RequestError("Error"),               # post-sitemap320: attempt 2
            httpx.RequestError("Error"),               # post-sitemap320: attempt 3
            _make_response(jo_post_sitemap_in_range),  # post-sitemap321: 3 articles
        ])

        discoverer = _make_discoverer(max_retries=3)

        # When
        articles = await discoverer.discover(news_source_id=2)

        # Then: 3 articles from the successful sitemap
        assert len(articles) == 3

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_failed_sitemaps_cleared_on_each_discover_call(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN a discoverer that had failures on a previous call
        WHEN discover() is called again and all sitemaps succeed
        THEN failed_sitemaps is reset to empty
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            # First discover(): post-sitemap320 fails all retries
            _make_response(jo_sitemap_index),
            httpx.RequestError("Error"),
            httpx.RequestError("Error"),
            httpx.RequestError("Error"),
            _make_response(jo_post_sitemap_in_range),
            # Second discover(): everything succeeds
            _make_response(jo_sitemap_index),
            _make_response(jo_post_sitemap_in_range),
            _make_response(jo_post_sitemap_in_range),
        ])

        discoverer = _make_discoverer(max_retries=3)

        # When
        await discoverer.discover(news_source_id=2)
        assert len(discoverer.failed_sitemaps) == 1  # First call had failures

        await discoverer.discover(news_source_id=2)

        # Then: failures cleared on second call
        assert len(discoverer.failed_sitemaps) == 0


class TestJamaicaObserverSitemapDiscovererSitemapIndexFiltering:
    """Test filtering of sitemaps by type and date range."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_filters_out_page_sitemaps(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN a sitemap index with page-sitemap1.xml entries
        WHEN discover() is called
        THEN page-sitemap URLs are never fetched
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),
            _make_response(jo_post_sitemap_in_range),
            _make_response(jo_post_sitemap_in_range),
        ])

        discoverer = _make_discoverer()

        # When
        await discoverer.discover(news_source_id=2)

        # Then: no call to page-sitemap1.xml
        called_urls = [str(c[0][0]) for c in mock_client.get.call_args_list]
        assert not any("page-sitemap" in url for url in called_urls)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_filters_out_sitemaps_outside_date_range(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN a sitemap index with sitemaps from 2002 and 2025 far outside June 2020
        WHEN discover() is called
        THEN only the two in-range sitemaps (320, 321) are fetched
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),
            _make_response(jo_post_sitemap_in_range),
            _make_response(jo_post_sitemap_in_range),
        ])

        discoverer = _make_discoverer()

        # When
        await discoverer.discover(news_source_id=2)

        # Then: old and new sitemaps never fetched; only 320 and 321
        called_urls = [str(c[0][0]) for c in mock_client.get.call_args_list]
        assert not any("post-sitemap1.xml" in url for url in called_urls)
        assert not any("post-sitemap500.xml" in url for url in called_urls)
        assert sum(1 for url in called_urls if "post-sitemap320.xml" in url) == 1
        assert sum(1 for url in called_urls if "post-sitemap321.xml" in url) == 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_sitemaps_fetched_in_numerical_order(
        self, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN a sitemap index listing post-sitemap320 and post-sitemap321 (not in order)
        WHEN discover() is called
        THEN they are fetched in ascending numerical order (320 before 321)
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),
            _make_response(jo_post_sitemap_in_range),
            _make_response(jo_post_sitemap_in_range),
        ])

        discoverer = _make_discoverer()

        # When
        await discoverer.discover(news_source_id=2)

        # Then: 2nd call is 320, 3rd call is 321
        called_urls = [str(c[0][0]) for c in mock_client.get.call_args_list]
        assert "post-sitemap320.xml" in called_urls[1]
        assert "post-sitemap321.xml" in called_urls[2]


class TestJamaicaObserverSitemapDiscovererCrawlDelay:
    """Test crawl delay behaviour between sitemap requests."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_no_crawl_delay_before_first_sitemap(
        self, mock_sleep, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN a discoverer with crawl_delay=1.5 and 2 sitemaps
        WHEN discover() is called
        THEN crawl delay is applied exactly once (between the two sitemaps, not before the first)
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),
            _make_response(jo_post_sitemap_in_range),
            _make_response(jo_post_sitemap_in_range),
        ])

        crawl_delay = 1.5
        discoverer = _make_discoverer(crawl_delay=crawl_delay)

        # When
        await discoverer.discover(news_source_id=2)

        # Then: exactly 1 crawl-delay sleep
        crawl_sleep_calls = [c for c in mock_sleep.call_args_list if c[0][0] == crawl_delay]
        assert len(crawl_sleep_calls) == 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_crawl_delay_value_is_respected(
        self, mock_sleep, mock_client_class, jo_sitemap_index, jo_post_sitemap_in_range
    ):
        """
        GIVEN a discoverer with crawl_delay=2.0
        WHEN discover() is called
        THEN asyncio.sleep is called with exactly 2.0
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(jo_sitemap_index),
            _make_response(jo_post_sitemap_in_range),
            _make_response(jo_post_sitemap_in_range),
        ])

        crawl_delay = 2.0
        discoverer = _make_discoverer(crawl_delay=crawl_delay)

        # When
        await discoverer.discover(news_source_id=2)

        # Then
        mock_sleep.assert_any_call(crawl_delay)
