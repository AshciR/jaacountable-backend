"""Tests for JamaicaGleanerSitemapDiscoverer."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.article_discovery.discoverers.jamaica_gleaner_sitemap_discoverer import (
    JamaicaGleanerSitemapDiscoverer,
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


def _make_discoverer(**kwargs) -> JamaicaGleanerSitemapDiscoverer:
    """Build a discoverer for June 2020 with fast settings for testing."""
    defaults = dict(
        start_date=_START,
        end_date=_END,
        base_backoff=0.01,
        crawl_delay=0.01,
    )
    defaults.update(kwargs)
    return JamaicaGleanerSitemapDiscoverer(**defaults)


class TestJamaicaGleanerSitemapDiscovererUrlsetFormat:
    """Test the primary urlset format (sitemap.xml returns <urlset> directly)."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discover_returns_discovered_articles(
        self, mock_client_class, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a discoverer configured for June 2020
        WHEN discover() is called and the sitemap returns a urlset directly
        THEN it returns a non-empty list of DiscoveredArticle instances
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=_make_response(gleaner_sitemap_urlset_in_range))

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert isinstance(articles, list)
        assert len(articles) > 0
        assert all(isinstance(a, DiscoveredArticle) for a in articles)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_discovered_articles_have_correct_fields(
        self, mock_client_class, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a urlset with 3 in-range news articles
        WHEN discover() is called
        THEN each article has correct url, news_source_id=1, section='news',
             title=slug, published_date from URL, and timezone-aware discovered_at
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=_make_response(gleaner_sitemap_urlset_in_range))

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then — verify fields on the June 15 article
        article = next(
            a for a in articles
            if a.url == "https://jamaica-gleaner.com/article/news/20200615/article-one-slug"
        )
        assert article.url == "https://jamaica-gleaner.com/article/news/20200615/article-one-slug"
        assert article.news_source_id == 1
        assert article.section == "news"
        assert article.title == "article-one-slug"
        assert article.published_date == datetime(2020, 6, 15, tzinfo=timezone.utc)
        assert article.discovered_at.tzinfo == timezone.utc

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_urlset_only_makes_one_http_request(
        self, mock_client_class, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a sitemap that returns a urlset directly
        WHEN discover() is called
        THEN only one HTTP request is made (no page fetches)
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=_make_response(gleaner_sitemap_urlset_in_range))

        discoverer = _make_discoverer()

        # When
        await discoverer.discover(news_source_id=1)

        # Then
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_urlset_filters_articles_outside_date_range(
        self, mock_client_class, gleaner_sitemap_urlset_mixed
    ):
        """
        GIVEN a urlset with URLs before, inside, and after the target range
        WHEN discover() is called
        THEN only the 2 in-range news articles are returned
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=_make_response(gleaner_sitemap_urlset_mixed))

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        urls = {a.url for a in articles}
        assert "https://jamaica-gleaner.com/article/news/20200620/first-in-range-slug" in urls
        assert "https://jamaica-gleaner.com/article/news/20200621/second-in-range-slug" in urls
        assert "https://jamaica-gleaner.com/article/news/20200531/before-start-slug" not in urls
        assert "https://jamaica-gleaner.com/article/news/20200701/after-end-slug" not in urls

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_urlset_filters_non_news_sections(
        self, mock_client_class, gleaner_sitemap_urlset_mixed
    ):
        """
        GIVEN a urlset with a sports article within the date range
        WHEN discover() is called
        THEN the sports article is excluded (only news section kept)
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=_make_response(gleaner_sitemap_urlset_mixed))

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        urls = {a.url for a in articles}
        assert "https://jamaica-gleaner.com/article/sports/20200621/sports-in-range-ignored" not in urls
        assert all(a.section == "news" for a in articles)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_urlset_skips_urls_without_date_pattern(
        self, mock_client_class, gleaner_sitemap_urlset_mixed
    ):
        """
        GIVEN a urlset containing non-article URLs (e.g. /news section page)
        WHEN discover() is called
        THEN those URLs are silently skipped
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=_make_response(gleaner_sitemap_urlset_mixed))

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        urls = {a.url for a in articles}
        assert "https://jamaica-gleaner.com/news" not in urls


class TestJamaicaGleanerSitemapDiscovererSitemapIndexFormat:
    """Test the sitemapindex format (sitemap.xml returns <sitemapindex> with pages)."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_sitemapindex_discovers_articles_across_all_pages(
        self, mock_client_class, gleaner_sitemap_index, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a sitemapindex with 2 pages, each with 3 in-range articles
        WHEN discover() is called
        THEN articles from both pages are returned
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(gleaner_sitemap_index),           # sitemap index
            _make_response(gleaner_sitemap_urlset_in_range), # page=1
            _make_response(gleaner_sitemap_urlset_in_range), # page=2
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then: 3 unique articles (both pages have same URLs, deduped)
        assert len(articles) == 3

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_sitemapindex_makes_correct_number_of_requests(
        self, mock_client_class, gleaner_sitemap_index, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a sitemapindex with 2 pages
        WHEN discover() is called
        THEN 3 total HTTP requests are made (index + page=1 + page=2)
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(gleaner_sitemap_index),
            _make_response(gleaner_sitemap_urlset_in_range),
            _make_response(gleaner_sitemap_urlset_in_range),
        ])

        discoverer = _make_discoverer()

        # When
        await discoverer.discover(news_source_id=1)

        # Then
        assert mock_client.get.call_count == 3

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_sitemapindex_pages_fetched_in_numerical_order(
        self, mock_client_class, gleaner_sitemap_index, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a sitemapindex with page=1 and page=2
        WHEN discover() is called
        THEN page=1 is fetched before page=2
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(gleaner_sitemap_index),
            _make_response(gleaner_sitemap_urlset_in_range),
            _make_response(gleaner_sitemap_urlset_in_range),
        ])

        discoverer = _make_discoverer()

        # When
        await discoverer.discover(news_source_id=1)

        # Then
        called_urls = [str(c[0][0]) for c in mock_client.get.call_args_list]
        assert "page=1" in called_urls[1]
        assert "page=2" in called_urls[2]

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_sitemapindex_deduplicates_articles_across_pages(
        self, mock_client_class, gleaner_sitemap_index, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN two pages that both return the same 3 article URLs
        WHEN discover() is called
        THEN duplicate URLs are removed, keeping 3 unique articles
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(gleaner_sitemap_index),
            _make_response(gleaner_sitemap_urlset_in_range),  # 3 articles
            _make_response(gleaner_sitemap_urlset_in_range),  # same 3 again
        ])

        discoverer = _make_discoverer()

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 3


class TestJamaicaGleanerSitemapDiscovererValidation:
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
            JamaicaGleanerSitemapDiscoverer(
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
            JamaicaGleanerSitemapDiscoverer(
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
            JamaicaGleanerSitemapDiscoverer(
                start_date=datetime(2020, 6, 30, tzinfo=timezone.utc),
                end_date=datetime(2020, 6, 1, tzinfo=timezone.utc),
            )


class TestJamaicaGleanerSitemapDiscovererNetworkErrors:
    """Test retry logic and failure handling."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_retry_on_network_error_succeeds_on_second_attempt(
        self, mock_client_class, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a transient network error on the first attempt
        WHEN discover() is called
        THEN it retries and succeeds on the second attempt
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            httpx.RequestError("Connection reset"),       # attempt 1 fails
            _make_response(gleaner_sitemap_urlset_in_range),  # attempt 2 succeeds
        ])

        discoverer = _make_discoverer(max_retries=3)

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) > 0
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_exponential_backoff_on_retries(
        self, mock_sleep, mock_client_class, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN two consecutive network errors before success
        WHEN discover() is called
        THEN it sleeps for 2^1=2s and 2^2=4s between retries
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            httpx.RequestError("Error 1"),                    # attempt 1
            httpx.RequestError("Error 2"),                    # attempt 2
            _make_response(gleaner_sitemap_urlset_in_range),  # attempt 3 succeeds
        ])

        discoverer = _make_discoverer(max_retries=3, base_backoff=2.0)

        # When
        await discoverer.discover(news_source_id=1)

        # Then: backoff sleeps at 2^1=2s and 2^2=4s
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        assert 2.0 in sleep_calls
        assert 4.0 in sleep_calls

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_failed_page_tracked_in_failed_sitemaps(
        self, mock_client_class, gleaner_sitemap_index, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a sitemapindex where page=1 fails all retry attempts
        WHEN discover() is called
        THEN the page identifier is recorded in discoverer.failed_sitemaps
        """
        # Given: index succeeds, page=1 fails all retries, page=2 succeeds
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(gleaner_sitemap_index),
            httpx.RequestError("Error"),               # page=1: attempt 1
            httpx.RequestError("Error"),               # page=1: attempt 2
            httpx.RequestError("Error"),               # page=1: attempt 3
            _make_response(gleaner_sitemap_urlset_in_range),  # page=2 succeeds
        ])

        discoverer = _make_discoverer(max_retries=3)

        # When
        await discoverer.discover(news_source_id=1)

        # Then
        assert len(discoverer.failed_sitemaps) == 1
        assert "page=1" in discoverer.failed_sitemaps[0]

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_failed_page_fail_soft_continues_other_pages(
        self, mock_client_class, gleaner_sitemap_index, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a sitemapindex where page=1 fails all retries
        WHEN discover() is called
        THEN page=2 is still processed (fail-soft) and its articles returned
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(gleaner_sitemap_index),
            httpx.RequestError("Error"),
            httpx.RequestError("Error"),
            httpx.RequestError("Error"),
            _make_response(gleaner_sitemap_urlset_in_range),  # page=2: 3 articles
        ])

        discoverer = _make_discoverer(max_retries=3)

        # When
        articles = await discoverer.discover(news_source_id=1)

        # Then
        assert len(articles) == 3

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_failed_sitemaps_cleared_on_each_discover_call(
        self, mock_client_class, gleaner_sitemap_index, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a discoverer that had failures on a previous call
        WHEN discover() is called again and all pages succeed
        THEN failed_sitemaps is reset to empty
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            # First discover(): page=1 fails all retries
            _make_response(gleaner_sitemap_index),
            httpx.RequestError("Error"),
            httpx.RequestError("Error"),
            httpx.RequestError("Error"),
            _make_response(gleaner_sitemap_urlset_in_range),
            # Second discover(): everything succeeds (urlset directly)
            _make_response(gleaner_sitemap_urlset_in_range),
        ])

        discoverer = _make_discoverer(max_retries=3)

        # When
        await discoverer.discover(news_source_id=1)
        assert len(discoverer.failed_sitemaps) == 1

        await discoverer.discover(news_source_id=1)

        # Then
        assert len(discoverer.failed_sitemaps) == 0


class TestJamaicaGleanerSitemapDiscovererCrawlDelay:
    """Test crawl delay behaviour between page requests (sitemapindex path only)."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_no_crawl_delay_before_first_page(
        self, mock_sleep, mock_client_class, gleaner_sitemap_index, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a sitemapindex with 2 pages and crawl_delay=1.5
        WHEN discover() is called
        THEN crawl delay is applied exactly once (between the two pages, not before the first)
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(gleaner_sitemap_index),
            _make_response(gleaner_sitemap_urlset_in_range),
            _make_response(gleaner_sitemap_urlset_in_range),
        ])

        crawl_delay = 1.5
        discoverer = _make_discoverer(crawl_delay=crawl_delay)

        # When
        await discoverer.discover(news_source_id=1)

        # Then: exactly 1 crawl-delay sleep
        crawl_sleep_calls = [c for c in mock_sleep.call_args_list if c[0][0] == crawl_delay]
        assert len(crawl_sleep_calls) == 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_crawl_delay_value_is_respected(
        self, mock_sleep, mock_client_class, gleaner_sitemap_index, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a sitemapindex with crawl_delay=2.0
        WHEN discover() is called
        THEN asyncio.sleep is called with exactly 2.0
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=[
            _make_response(gleaner_sitemap_index),
            _make_response(gleaner_sitemap_urlset_in_range),
            _make_response(gleaner_sitemap_urlset_in_range),
        ])

        crawl_delay = 2.0
        discoverer = _make_discoverer(crawl_delay=crawl_delay)

        # When
        await discoverer.discover(news_source_id=1)

        # Then
        mock_sleep.assert_any_call(crawl_delay)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    @patch("asyncio.sleep")
    async def test_no_crawl_delay_for_urlset_format(
        self, mock_sleep, mock_client_class, gleaner_sitemap_urlset_in_range
    ):
        """
        GIVEN a sitemap that returns a urlset directly (single fetch)
        WHEN discover() is called
        THEN no crawl delay sleep is applied
        """
        # Given
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=_make_response(gleaner_sitemap_urlset_in_range))

        crawl_delay = 1.5
        discoverer = _make_discoverer(crawl_delay=crawl_delay)

        # When
        await discoverer.discover(news_source_id=1)

        # Then: no sleep at the crawl_delay value
        crawl_sleep_calls = [c for c in mock_sleep.call_args_list if c[0][0] == crawl_delay]
        assert len(crawl_sleep_calls) == 0
