"""Tests for GleanerExtractor strategy (December 2025 site structure)."""
import pytest
from datetime import datetime, timezone

from src.article_extractor.gleaner_extractor import GleanerExtractor
from src.article_extractor.models import ExtractedArticleContent


class TestGleanerExtractorHappyPath:
    """Happy path tests for Gleaner extraction with JSON-LD + CSS hybrid parsing."""

    async def test_extract_complete_article(self, gleaner_html: str):
        # Given: valid Gleaner article HTML with JSON-LD and all elements
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/20251210/embrace-one-health"

        # When: extracting content
        content = extractor.extract(gleaner_html, url)

        # Then: all fields are extracted correctly from JSON-LD and CSS
        assert isinstance(content, ExtractedArticleContent)

        # Title from JSON-LD (with curly quotes U+2018/U+2019 and trailing space stripped)
        assert content.title == "Embrace \u2018One Health\u2019"

        # Full text from CSS (article--body)
        assert content.full_text is not None
        assert content.full_text.startswith("Medical experts are calling for stronger adherence to the global One Health mandate")

        # Author from JSON-LD (cleaned)
        assert content.author == "Corey Robinson"

        # Published date from JSON-LD (converted to UTC)
        assert content.published_date is not None
        assert content.published_date.year == 2025
        assert content.published_date.month == 12
        assert content.published_date.day == 10
        assert content.published_date.tzinfo == timezone.utc

    async def test_author_name_cleaned(self, gleaner_html: str):
        # Given: Gleaner article HTML with author in format "Name/Staff Reporter"
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/20251210/embrace-one-health"

        # When: extracting content
        content = extractor.extract(gleaner_html, url)

        # Then: "/Staff Reporter" suffix is removed from author name
        assert content.author == "Corey Robinson"
        assert "/Staff Reporter" not in content.author
        assert "By " not in content.author

    async def test_json_ld_missing_falls_back_to_css(self):
        # Given: HTML without JSON-LD but with CSS selectors (new site structure)
        html = """
        <html>
            <body>
                <h1 class="article--title">Test Article Title</h1>
                <div class="article--body">
                    <p>First paragraph of content that is long enough to pass validation.</p>
                    <p>Second paragraph with more content.</p>
                </div>
                <div class="article--authors">Jane Doe/Staff Reporter</div>
                <meta property="article:published_time" content="2025-12-10T12:00:00-05:00">
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: extraction succeeds using CSS fallbacks
        assert content.title == "Test Article Title"
        assert content.full_text.startswith("First paragraph of content")
        assert content.author == "Jane Doe"
        assert content.published_date is not None

    async def test_json_ld_malformed_falls_back_to_css(self):
        # Given: HTML with malformed JSON-LD but valid CSS selectors
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                    { invalid json here }
                </script>
            </head>
            <body>
                <h1 class="article--title">Fallback Title</h1>
                <div class="article--body">
                    <p>Content paragraph that is long enough to meet minimum requirements for extraction.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content (should not crash)
        content = extractor.extract(html, url)

        # Then: extraction succeeds using CSS fallbacks
        assert content.title == "Fallback Title"
        assert content.full_text.startswith("Content paragraph")

    async def test_fallback_to_legacy_css_selectors_works(self):
        # Given: HTML with legacy CSS classes (no JSON-LD, no new classes)
        html = """
        <html>
            <body>
                <h1 class="title">Legacy Title</h1>
                <div class="article-content">
                    <p>Legacy content paragraph with enough text to pass validation requirements.</p>
                    <p>Second paragraph of legacy content.</p>
                </div>
                <a class="author-term">Legacy Author/Staff Reporter</a>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/legacy"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: extraction succeeds using legacy CSS fallbacks
        assert content.title == "Legacy Title"
        assert content.full_text.startswith("Legacy content paragraph")
        assert content.author == "Legacy Author"

    async def test_mixed_json_ld_and_css(self):
        # Given: HTML with JSON-LD for metadata but CSS for body
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": "Mixed Source Title",
                    "author": {
                        "@type": "Person",
                        "name": "Mixed Author"
                    },
                    "datePublished": "2025-12-10T10:00:00-05:00"
                }
                </script>
            </head>
            <body>
                <div class="article--body">
                    <p>Body content from CSS selector with sufficient length for validation.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/mixed"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: metadata from JSON-LD, body from CSS
        assert content.title == "Mixed Source Title"
        assert content.author == "Mixed Author"
        assert content.published_date is not None
        assert content.full_text.startswith("Body content from CSS")


class TestGleanerExtractorParsingErrors:
    """Parsing error tests for Gleaner extraction."""

    async def test_missing_title_all_sources_raises_value_error(self):
        # Given: HTML without title in JSON-LD or any CSS selector
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "author": {"@type": "Person", "name": "Author"}
                }
                </script>
            </head>
            <body>
                <div class="article--body"><p>Content without title</p></div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "Could not extract title" in str(exc_info.value)
        assert url in str(exc_info.value)

    async def test_missing_content_all_sources_raises_value_error(self):
        # Given: HTML without article content container in any CSS selector
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": "Title Only"
                }
                </script>
            </head>
            <body>
                <h1>Title Only</h1>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "content container" in str(exc_info.value).lower()
        assert url in str(exc_info.value)

    async def test_empty_content_div_raises_value_error(self):
        # Given: HTML with content container but no paragraphs
        html = """
        <html>
            <body>
                <h1 class="article--title">Test Title</h1>
                <div class="article--body">
                    <div>Some div content but no paragraphs</div>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "No paragraphs found" in str(exc_info.value)
        assert url in str(exc_info.value)

    async def test_too_short_text_raises_value_error(self):
        # Given: HTML with content that is too short (< 50 characters)
        html = """
        <html>
            <body>
                <h1 class="article--title">Title</h1>
                <div class="article--body">
                    <p>Short</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When/Then: extraction raises ValueError
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(html, url)

        assert "too short" in str(exc_info.value).lower()
        assert url in str(exc_info.value)

    async def test_json_ld_invalid_json_gracefully_degrades(self):
        # Given: HTML with invalid JSON in JSON-LD script tag
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                    { "invalid": json, missing: quotes }
                </script>
            </head>
            <body>
                <h1 class="article--title">Fallback Title</h1>
                <div class="article--body">
                    <p>Content that will be extracted despite invalid JSON-LD with enough length.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content (should not crash)
        content = extractor.extract(html, url)

        # Then: extraction succeeds using CSS fallbacks
        assert content.title == "Fallback Title"
        assert content.full_text.startswith("Content that will be extracted")


class TestGleanerExtractorEdgeCases:
    """Edge case tests for Gleaner extraction."""

    async def test_missing_author_returns_none(self):
        # Given: HTML without author in JSON-LD or any CSS selector
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": "No Author Article"
                }
                </script>
            </head>
            <body>
                <div class="article--body">
                    <p>Article content without author information that meets length requirements.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: author is None (optional field)
        assert content.author is None

    async def test_missing_date_returns_none(self):
        # Given: HTML without date in JSON-LD or any CSS selector
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": "No Date Article"
                }
                </script>
            </head>
            <body>
                <div class="article--body">
                    <p>Article content without publication date that has sufficient length.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: published_date is None (optional field)
        assert content.published_date is None

    async def test_json_ld_missing_headline_falls_back(self):
        # Given: JSON-LD without headline field
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "author": {"@type": "Person", "name": "Someone"}
                }
                </script>
            </head>
            <body>
                <h1 class="article--title">CSS Fallback Title</h1>
                <div class="article--body">
                    <p>Content extracted from CSS with adequate length for validation.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: title extracted from CSS fallback
        assert content.title == "CSS Fallback Title"

    async def test_json_ld_author_not_person_type(self):
        # Given: JSON-LD with author but not Person type
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": "Article Title",
                    "author": {
                        "@type": "Organization",
                        "name": "News Org"
                    }
                }
                </script>
            </head>
            <body>
                <div class="article--body">
                    <p>Content with organization author instead of person with sufficient length.</p>
                </div>
                <div class="article--authors">Fallback Author</div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: falls back to CSS selector for author
        assert content.author == "Fallback Author"

    async def test_date_parsing_error_returns_none(self):
        # Given: JSON-LD with invalid date format
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": "Article",
                    "datePublished": "not-a-valid-date"
                }
                </script>
            </head>
            <body>
                <div class="article--body">
                    <p>Content with invalid date that still meets length requirements.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: published_date is None (graceful degradation)
        assert content.published_date is None

    async def test_unicode_content_in_json_ld(self):
        # Given: JSON-LD with Unicode characters in headline and author
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": "Café Résumé: A Story",
                    "author": {
                        "@type": "Person",
                        "name": "José García"
                    }
                }
                </script>
            </head>
            <body>
                <div class="article--body">
                    <p>Content with Unicode characters: café, résumé, naïve with sufficient length.</p>
                </div>
            </body>
        </html>
        """
        extractor = GleanerExtractor()
        url = "https://jamaica-gleaner.com/article/news/test"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: Unicode characters preserved correctly
        assert content.title == "Café Résumé: A Story"
        assert content.author == "José García"


class TestGleanerExtractorJsonLdParsing:
    """Tests specifically for JSON-LD parsing logic."""

    async def test_extract_json_ld_success(self):
        # Given: HTML with valid JSON-LD Article
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": "Test"
                }
                </script>
            </head>
        </html>
        """
        extractor = GleanerExtractor()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        # When: extracting JSON-LD
        json_ld = extractor._extract_json_ld(soup)

        # Then: JSON-LD is parsed correctly
        assert json_ld is not None
        assert json_ld["@type"] == "Article"
        assert json_ld["headline"] == "Test"

    async def test_extract_json_ld_missing_returns_none(self):
        # Given: HTML without JSON-LD script tag
        html = """
        <html>
            <head>
                <title>No JSON-LD</title>
            </head>
        </html>
        """
        extractor = GleanerExtractor()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        # When: extracting JSON-LD
        json_ld = extractor._extract_json_ld(soup)

        # Then: returns None
        assert json_ld is None

    async def test_extract_json_ld_invalid_json_returns_none(self):
        # Given: HTML with invalid JSON in script tag
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                    { invalid json }
                </script>
            </head>
        </html>
        """
        extractor = GleanerExtractor()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        # When: extracting JSON-LD
        json_ld = extractor._extract_json_ld(soup)

        # Then: returns None (graceful error handling)
        assert json_ld is None

    async def test_extract_json_ld_multiple_scripts_finds_article(self):
        # Given: HTML with multiple JSON-LD blocks, one is Article type
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "WebSite",
                    "name": "Test Site"
                }
                </script>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": "The Article"
                }
                </script>
            </head>
        </html>
        """
        extractor = GleanerExtractor()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        # When: extracting JSON-LD
        json_ld = extractor._extract_json_ld(soup)

        # Then: finds the Article type JSON-LD
        assert json_ld is not None
        assert json_ld["@type"] == "Article"
        assert json_ld["headline"] == "The Article"
