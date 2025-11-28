"""Tests for ArticleExtractionService."""
import pytest

from src.services.article_extractor.service import (
    ArticleExtractionService,
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
        service = ArticleExtractionService()
        url = "https://example.com/article/test"

        # When/Then: extracting content raises ValueError
        with pytest.raises(ValueError) as exc_info:
            service.extract_article_content(url)

        # Then: error message includes the unsupported domain and supported domains
        error_msg = str(exc_info.value)
        assert "Unsupported domain: example.com" in error_msg
        assert "Supported domains:" in error_msg
        assert "jamaica-gleaner.com" in error_msg

    async def test_unsupported_subdomain_raises_value_error(self):
        # Given: a URL with subdomain from unsupported site
        service = ArticleExtractionService()
        url = "https://news.bbc.com/article/test"

        # When/Then: extracting content raises ValueError
        with pytest.raises(ValueError) as exc_info:
            service.extract_article_content(url)

        # Then: error message indicates unsupported domain
        error_msg = str(exc_info.value)
        assert "Unsupported domain: news.bbc.com" in error_msg
        assert "jamaica-gleaner.com" in error_msg

    async def test_error_message_lists_all_supported_domains(self):
        # Given: a URL from an unsupported domain
        service = ArticleExtractionService()
        url = "https://unsupported-news.com/article/test"

        # When/Then: extracting content raises ValueError with all supported domains
        with pytest.raises(ValueError) as exc_info:
            service.extract_article_content(url)

        error_msg = str(exc_info.value)
        # Then: error message includes all domains from extractors dict
        for domain in service.extractors.keys():
            assert domain in error_msg
