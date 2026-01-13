"""Tests for DefaultArticleExtractionService."""
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.article_extractor.service import (
    DefaultArticleExtractionService,
    _parse_and_validate_url,
)


class TestParseAndValidateUrl:
    """Tests for _parse_and_validate_url function."""

    async def test_valid_url_returns_domain(self):
        # Given: a valid Gleaner URL
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: parsing and validating the URL
        domain = _parse_and_validate_url(url)

        # Then: returns the normalized domain
        assert domain == "jamaica-gleaner.com"

    async def test_url_with_www_prefix_strips_www(self):
        # Given: a URL with www. prefix
        url = "https://www.jamaica-gleaner.com/article/news/test"

        # When: parsing and validating the URL
        domain = _parse_and_validate_url(url)

        # Then: www. prefix is removed
        assert domain == "jamaica-gleaner.com"

    async def test_url_with_http_scheme(self):
        # Given: a URL with http (not https)
        url = "http://jamaica-gleaner.com/article/news/test"

        # When: parsing and validating the URL
        domain = _parse_and_validate_url(url)

        # Then: domain is extracted correctly
        assert domain == "jamaica-gleaner.com"

    async def test_domain_normalized_to_lowercase(self):
        # Given: a URL with mixed case domain
        url = "https://Jamaica-Gleaner.COM/article/news/test"

        # When: parsing and validating the URL
        domain = _parse_and_validate_url(url)

        # Then: domain is converted to lowercase
        assert domain == "jamaica-gleaner.com"

    async def test_url_with_leading_trailing_whitespace(self):
        # Given: a URL with whitespace
        url = "  https://jamaica-gleaner.com/article/news/test  "

        # When: parsing and validating the URL
        domain = _parse_and_validate_url(url)

        # Then: whitespace is stripped and domain extracted
        assert domain == "jamaica-gleaner.com"

    async def test_empty_url_raises_value_error(self):
        # Given: an empty URL
        url = ""

        # When/Then: parsing raises ValueError
        with pytest.raises(ValueError) as exc_info:
            _parse_and_validate_url(url)

        assert "URL cannot be empty" in str(exc_info.value)

    async def test_whitespace_only_url_raises_value_error(self):
        # Given: a whitespace-only URL
        url = "   "

        # When/Then: parsing raises ValueError
        with pytest.raises(ValueError) as exc_info:
            _parse_and_validate_url(url)

        assert "URL cannot be empty" in str(exc_info.value)

    async def test_url_without_scheme_raises_value_error(self):
        # Given: a URL without http/https scheme
        url = "jamaica-gleaner.com/article/news/test"

        # When/Then: parsing raises ValueError
        with pytest.raises(ValueError) as exc_info:
            _parse_and_validate_url(url)

        assert "URL must include scheme and domain" in str(exc_info.value)

    async def test_url_without_domain_raises_value_error(self):
        # Given: a malformed URL without domain
        url = "https://"

        # When/Then: parsing raises ValueError
        with pytest.raises(ValueError) as exc_info:
            _parse_and_validate_url(url)

        assert "URL must include scheme and domain" in str(exc_info.value)

    async def test_url_with_only_scheme_raises_value_error(self):
        # Given: a URL with scheme but no netloc
        url = "https:///article/test"

        # When/Then: parsing raises ValueError
        with pytest.raises(ValueError) as exc_info:
            _parse_and_validate_url(url)

        assert "URL must include scheme and domain" in str(exc_info.value)


class TestUnsupportedDomain:
    """Tests for unsupported domain error handling."""

    async def test_unsupported_domain_raises_value_error(self):
        # Given: a URL from an unsupported domain
        service = DefaultArticleExtractionService()
        url = "https://example.com/article/test"

        # When/Then: extracting content raises ValueError
        with pytest.raises(ValueError) as exc_info:
            await service.extract_article_content(url)

        # Then: error message includes the unsupported domain and supported domains
        error_msg = str(exc_info.value)
        assert "Unsupported domain: example.com" in error_msg
        assert "Supported domains:" in error_msg
        assert "jamaica-gleaner.com" in error_msg

    async def test_unsupported_subdomain_raises_value_error(self):
        # Given: a URL with subdomain from unsupported site
        service = DefaultArticleExtractionService()
        url = "https://news.bbc.com/article/test"

        # When/Then: extracting content raises ValueError
        with pytest.raises(ValueError) as exc_info:
            await service.extract_article_content(url)

        # Then: error message indicates unsupported domain
        error_msg = str(exc_info.value)
        assert "Unsupported domain: news.bbc.com" in error_msg
        assert "jamaica-gleaner.com" in error_msg

    async def test_error_message_lists_all_supported_domains(self):
        # Given: a URL from an unsupported domain
        service = DefaultArticleExtractionService()
        url = "https://unsupported-news.com/article/test"

        # When/Then: extracting content raises ValueError with all supported domains
        with pytest.raises(ValueError) as exc_info:
            await service.extract_article_content(url)

        error_msg = str(exc_info.value)
        # Then: error message includes all domains from extractors dict
        for domain in service.extractors.keys():
            assert domain in error_msg


class TestFetchHtmlRetryLogic:
    """Tests for _fetch_html retry logic with exponential backoff via extract_article_content."""

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_extract_succeeds_on_first_attempt(
        self, mock_async_client_class, mock_sleep, gleaner_html_v2
    ):
        """
        Given: a valid URL that returns HTML on first attempt
        When: extract_article_content() is called
        Then: it returns extracted content without retrying
        """
        # Given: Mock successful HTTP response with real Gleaner HTML
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = Mock()
        mock_response.text = gleaner_html_v2
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_client.get = AsyncMock(return_value=mock_response)

        # When: Extracting article content
        service = DefaultArticleExtractionService()
        content = await service.extract_article_content(
            "https://jamaica-gleaner.com/article/news/test"
        )

        # Then: Returns extracted content, calls get() once
        assert "One Health" in content.title
        assert mock_client.get.call_count == 1
        mock_sleep.assert_not_called()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_extract_retries_on_503_then_succeeds(
        self, mock_async_client_class, mock_sleep, gleaner_html_v2
    ):
        """
        Given: a 503 Service Unavailable on first attempt, then success
        When: extract_article_content() is called
        Then: it retries with exponential backoff and succeeds
        """
        # Given: Mock HTTP client
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client

        # Create 503 error
        mock_503_response = Mock()
        mock_503_response.status_code = 503
        mock_503_response.reason_phrase = "Service Unavailable"
        error_503 = httpx.HTTPStatusError(
            message="503 Service Unavailable",
            request=Mock(),
            response=mock_503_response,
        )

        # Create success response with real Gleaner HTML
        mock_success_response = Mock()
        mock_success_response.text = gleaner_html_v2
        mock_success_response.status_code = 200
        mock_success_response.raise_for_status = Mock()

        # Setup: fail once with 503, then succeed
        mock_client.get = AsyncMock(side_effect=[error_503, mock_success_response])

        # When: Extracting article content
        service = DefaultArticleExtractionService()
        content = await service.extract_article_content(
            "https://jamaica-gleaner.com/article/news/test"
        )

        # Then: Returns content after retry
        assert "One Health" in content.title
        assert mock_client.get.call_count == 2

        # Verify exponential backoff (2^1 = 2 seconds)
        mock_sleep.assert_called_once_with(2.0)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_extract_fails_after_max_retries_on_500(
        self, mock_async_client_class, mock_sleep
    ):
        """
        Given: persistent 500 Internal Server Error
        When: extract_article_content() is called
        Then: it retries 3 times then raises HTTPStatusError
        """
        # Given: Mock client that always returns 500
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client

        mock_500_response = Mock()
        mock_500_response.status_code = 500
        mock_500_response.reason_phrase = "Internal Server Error"
        error_500 = httpx.HTTPStatusError(
            message="500 Internal Server Error",
            request=Mock(),
            response=mock_500_response,
        )

        mock_client.get = AsyncMock(side_effect=error_500)

        # When/Then: Raises HTTPStatusError after max retries
        service = DefaultArticleExtractionService()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await service.extract_article_content(
                "https://jamaica-gleaner.com/article/news/test"
            )

        assert exc_info.value.response.status_code == 500
        assert mock_client.get.call_count == 3  # MAX_RETRIES

        # Verify exponential backoff: 2^1=2s, 2^2=4s
        assert mock_sleep.call_count == 2
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls == [2.0, 4.0]

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_extract_does_not_retry_on_404(
        self, mock_async_client_class, mock_sleep
    ):
        """
        Given: a 404 Not Found error
        When: extract_article_content() is called
        Then: it fails immediately WITHOUT retrying (4xx = client error)
        """
        # Given: Mock client that returns 404
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client

        mock_404_response = Mock()
        mock_404_response.status_code = 404
        mock_404_response.reason_phrase = "Not Found"
        error_404 = httpx.HTTPStatusError(
            message="404 Not Found",
            request=Mock(),
            response=mock_404_response,
        )

        mock_client.get = AsyncMock(side_effect=error_404)

        # When/Then: Raises HTTPStatusError immediately
        service = DefaultArticleExtractionService()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await service.extract_article_content(
                "https://jamaica-gleaner.com/article/news/test"
            )

        assert exc_info.value.response.status_code == 404
        assert mock_client.get.call_count == 1  # NO RETRIES
        mock_sleep.assert_not_called()  # NO BACKOFF

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_extract_does_not_retry_on_403(
        self, mock_async_client_class, mock_sleep
    ):
        """
        Given: a 403 Forbidden error
        When: extract_article_content() is called
        Then: it fails immediately WITHOUT retrying
        """
        # Given: Mock client that returns 403
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client

        mock_403_response = Mock()
        mock_403_response.status_code = 403
        mock_403_response.reason_phrase = "Forbidden"
        error_403 = httpx.HTTPStatusError(
            message="403 Forbidden",
            request=Mock(),
            response=mock_403_response,
        )

        mock_client.get = AsyncMock(side_effect=error_403)

        # When/Then: Raises HTTPStatusError immediately
        service = DefaultArticleExtractionService()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await service.extract_article_content(
                "https://jamaica-gleaner.com/article/news/test"
            )

        assert exc_info.value.response.status_code == 403
        assert mock_client.get.call_count == 1  # NO RETRIES
        mock_sleep.assert_not_called()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_extract_retries_on_network_error(
        self, mock_async_client_class, mock_sleep, gleaner_html_v2
    ):
        """
        Given: a network timeout on first attempt
        When: extract_article_content() is called
        Then: it retries and succeeds on second attempt
        """
        # Given: Mock client that fails once with network error, then succeeds
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client

        network_error = httpx.RequestError("Connection timeout")

        mock_success_response = Mock()
        mock_success_response.text = gleaner_html_v2
        mock_success_response.status_code = 200
        mock_success_response.raise_for_status = Mock()

        mock_client.get = AsyncMock(side_effect=[network_error, mock_success_response])

        # When: Extracting article content
        service = DefaultArticleExtractionService()
        content = await service.extract_article_content(
            "https://jamaica-gleaner.com/article/news/test"
        )

        # Then: Returns content after retry
        assert "One Health" in content.title
        assert mock_client.get.call_count == 2
        mock_sleep.assert_called_once_with(2.0)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_extract_uses_exponential_backoff(
        self, mock_async_client_class, mock_sleep, gleaner_html_v2
    ):
        """
        Given: multiple 502 Bad Gateway errors
        When: extract_article_content() is called
        Then: it uses exponential backoff: 2^1=2s, 2^2=4s
        """
        # Given: Mock client with two 502 errors, then success
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client

        mock_502_response = Mock()
        mock_502_response.status_code = 502
        mock_502_response.reason_phrase = "Bad Gateway"
        error_502 = httpx.HTTPStatusError(
            message="502 Bad Gateway",
            request=Mock(),
            response=mock_502_response,
        )

        mock_success_response = Mock()
        mock_success_response.text = gleaner_html_v2
        mock_success_response.status_code = 200
        mock_success_response.raise_for_status = Mock()

        mock_client.get = AsyncMock(
            side_effect=[error_502, error_502, mock_success_response]
        )

        # When: Extracting article content
        service = DefaultArticleExtractionService()
        content = await service.extract_article_content(
            "https://jamaica-gleaner.com/article/news/test"
        )

        # Then: Exponential backoff applied
        assert "One Health" in content.title
        assert mock_client.get.call_count == 3
        assert mock_sleep.call_count == 2

        # Verify backoff times: 2^1=2s, 2^2=4s
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls == [2.0, 4.0]

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_extract_retries_503_but_fails_on_404(
        self, mock_async_client_class, mock_sleep
    ):
        """
        Given: a 503 error followed by 404 error
        When: extract_article_content() is called
        Then: it retries 503 but fails immediately on 404
        """
        # Given: Mock client with 503, then 404
        mock_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = mock_client

        mock_503_response = Mock()
        mock_503_response.status_code = 503
        mock_503_response.reason_phrase = "Service Unavailable"
        error_503 = httpx.HTTPStatusError(
            message="503 Service Unavailable",
            request=Mock(),
            response=mock_503_response,
        )

        mock_404_response = Mock()
        mock_404_response.status_code = 404
        mock_404_response.reason_phrase = "Not Found"
        error_404 = httpx.HTTPStatusError(
            message="404 Not Found",
            request=Mock(),
            response=mock_404_response,
        )

        mock_client.get = AsyncMock(side_effect=[error_503, error_404])

        # When/Then: Raises 404 error after one retry
        service = DefaultArticleExtractionService()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await service.extract_article_content(
                "https://jamaica-gleaner.com/article/news/test"
            )

        assert exc_info.value.response.status_code == 404
        assert mock_client.get.call_count == 2  # 503 + 404
        assert mock_sleep.call_count == 1  # Only sleep after 503


class TestConnectionPoolingWithContextManager:
    """Tests for connection pooling via async context manager."""

    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_context_manager_creates_pooled_client(
        self, mock_async_client_class
    ):
        """Verify __aenter__ creates HTTP client."""
        # Given: mock client with aclose method
        mock_client = Mock()
        mock_client.aclose = AsyncMock()
        mock_async_client_class.return_value = mock_client

        # When: using service as context manager
        service = DefaultArticleExtractionService()
        async with service as s:
            # Then: service returns self and stores client
            assert s is service
            assert hasattr(service, "_http_client")
            assert service._http_client is mock_client

        # Then: client is closed on exit
        mock_client.aclose.assert_called_once()

    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_context_manager_reuses_client_across_extractions(
        self, mock_async_client_class, gleaner_html_v2
    ):
        """Verify same client is reused for multiple extractions."""
        # Given: mock client and response
        mock_client = Mock()
        mock_client.aclose = AsyncMock()
        mock_async_client_class.return_value = mock_client

        mock_response = Mock()
        mock_response.text = gleaner_html_v2
        mock_response.raise_for_status = Mock()
        mock_client.get = AsyncMock(return_value=mock_response)

        # When: extracting multiple articles with context manager
        service = DefaultArticleExtractionService()
        async with service:
            await service.extract_article_content(
                "https://jamaica-gleaner.com/article/news/1"
            )
            await service.extract_article_content(
                "https://jamaica-gleaner.com/article/news/2"
            )
            await service.extract_article_content(
                "https://jamaica-gleaner.com/article/news/3"
            )

        # Then: client created only ONCE (pooling!)
        assert mock_async_client_class.call_count == 1
        # Then: client used for all 3 extractions
        assert mock_client.get.call_count == 3
        # Then: client closed once at end
        mock_client.aclose.assert_called_once()

    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_context_manager_cleanup_on_error(self, mock_async_client_class):
        """Verify client is closed even if extraction fails."""
        # Given: mock client that raises error on get
        mock_client = Mock()
        mock_client.aclose = AsyncMock()
        mock_async_client_class.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=Exception("Network error"))

        # When: extraction fails inside context manager
        service = DefaultArticleExtractionService()
        with pytest.raises(Exception):
            async with service:
                await service.extract_article_content(
                    "https://jamaica-gleaner.com/test"
                )

        # Then: client still closed despite error
        mock_client.aclose.assert_called_once()

    @patch("src.article_extractor.service.httpx.AsyncClient")
    async def test_backward_compatibility_without_context_manager(
        self, mock_async_client_class, gleaner_html_v2
    ):
        """Verify service still works WITHOUT context manager (backward compatibility)."""
        # Given: mock temporary client (created in extract_article_content fallback)
        mock_temp_client = Mock()
        mock_async_client_class.return_value.__aenter__.return_value = (
            mock_temp_client
        )

        mock_response = Mock()
        mock_response.text = gleaner_html_v2
        mock_response.raise_for_status = Mock()
        mock_temp_client.get = AsyncMock(return_value=mock_response)

        # When: using service WITHOUT context manager (legacy usage)
        service = DefaultArticleExtractionService()
        content = await service.extract_article_content(
            "https://jamaica-gleaner.com/article/news/test"
        )

        # Then: extraction succeeds with temporary client
        assert "One Health" in content.title
        assert mock_temp_client.get.call_count == 1
