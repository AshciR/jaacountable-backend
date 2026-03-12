"""Tests for JamaicaObserverExtractor (JSON-LD + CSS hybrid strategy)."""
import pytest
from datetime import timezone

from src.article_extractor.extractors.jamaica_observer_extractor import JamaicaObserverExtractor
from src.article_extractor.models import ExtractedArticleContent


class TestJamaicaObserverExtractorHappyPath:
    """Happy path tests using real fixture HTML from three live articles."""

    async def test_extract_complete_article_pipe_with_email(self, jamaica_observer_html: str):
        # Given: Jamaica Observer article with pipe-delimited author including email
        # URL: /2026/03/03/well-rebound/ — author "Daniel Blake | Sports Writer | blaked@..."
        extractor = JamaicaObserverExtractor()
        url = "https://www.jamaicaobserver.com/2026/03/03/well-rebound/"

        # When: extracting content
        content = extractor.extract(jamaica_observer_html, url)

        # Then: all fields are extracted correctly
        assert isinstance(content, ExtractedArticleContent)
        assert content.title == "\u2018WE\u2019LL REBOUND\u2019"
        assert content.full_text.startswith("JAMAICA missed the chance")
        assert content.author == "Daniel Blake"
        assert content.published_date is not None
        assert content.published_date.year == 2026
        assert content.published_date.month == 3
        assert content.published_date.day == 3
        assert content.published_date.tzinfo == timezone.utc

    async def test_extract_complete_article_by_prefix(self, jamaica_observer_html_by_prefix: str):
        # Given: Jamaica Observer article with space-delimited author and "BY" prefix
        # URL: /2026/03/12/defence-questions-cops-video-recording-klans-accused/
        # author "BY ALICIA DUNKLEY WILLIS Senior reporter dunkleywillisa@jamaicaobserver.com"
        extractor = JamaicaObserverExtractor()
        url = "https://www.jamaicaobserver.com/2026/03/12/defence-questions-cops-video-recording-klans-accused/"

        # When: extracting content
        content = extractor.extract(jamaica_observer_html_by_prefix, url)

        # Then: title and date are correct
        assert content.title == "Defence questions cops\u2019 video recording of Klans accused"
        assert content.full_text.startswith("VIDEO recordings")
        assert content.published_date is not None
        assert content.published_date.year == 2026
        assert content.published_date.month == 3
        assert content.published_date.day == 12
        assert content.published_date.tzinfo == timezone.utc
        # Author: "BY " removed and email removed; job title may remain (known site inconsistency)
        assert content.author is not None
        assert "ALICIA DUNKLEY WILLIS" in content.author
        assert "BY " not in content.author
        assert "@" not in content.author

    async def test_extract_complete_article_pipe_no_email(self, jamaica_observer_html_pipe_no_email: str):
        # Given: Jamaica Observer article with pipe-delimited author without email
        # URL: /2026/03/12/holness-accuses-bunting-bias-paac-mandate-squabble-continues/
        # author "Jerome Williams | Reporter"
        extractor = JamaicaObserverExtractor()
        url = "https://www.jamaicaobserver.com/2026/03/12/holness-accuses-bunting-bias-paac-mandate-squabble-continues/"

        # When: extracting content
        content = extractor.extract(jamaica_observer_html_pipe_no_email, url)

        # Then: all fields extracted correctly
        assert content.title == "Holness accuses Bunting of bias as PAAC mandate squabble continues"
        assert content.author == "Jerome Williams"
        assert content.full_text.startswith("The increasingly tense")
        assert content.published_date is not None
        assert content.published_date.tzinfo == timezone.utc

    async def test_published_date_normalized_to_utc(self, jamaica_observer_html: str):
        # Given: article with datePublished in -05:00 offset
        extractor = JamaicaObserverExtractor()

        # When: extracting content
        content = extractor.extract(jamaica_observer_html, "https://www.jamaicaobserver.com/2026/03/03/well-rebound/")

        # Then: date is normalized to UTC (05:12 -05:00 = 10:12 UTC)
        assert content.published_date is not None
        assert content.published_date.tzinfo == timezone.utc
        assert content.published_date.hour == 10
        assert content.published_date.minute == 12

    async def test_json_ld_missing_falls_back_to_css(self):
        # Given: HTML without JSON-LD but with CSS selectors present
        html = """
        <html>
            <body>
                <h1 class="title">Test Article Title</h1>
                <div class="body content-single-wrap">
                    <p>First paragraph of content that is long enough to pass validation checks.</p>
                    <p>Second paragraph with more article content for the test.</p>
                </div>
                <span class="author">Jane Doe | Staff Reporter</span>
                <meta property="article:published_time" content="2026-03-03T10:00:00+00:00">
            </body>
        </html>
        """
        extractor = JamaicaObserverExtractor()
        url = "https://www.jamaicaobserver.com/2026/03/03/test/"

        # When: extracting content
        content = extractor.extract(html, url)

        # Then: extraction succeeds using CSS fallbacks
        assert content.title == "Test Article Title"
        assert content.full_text.startswith("First paragraph")
        assert content.author == "Jane Doe"
        assert content.published_date is not None
        assert content.published_date.tzinfo == timezone.utc


class TestJamaicaObserverExtractorMissingFields:
    """Tests for missing required and optional fields."""

    async def test_missing_title_raises_value_error(self):
        # Given: HTML without any title elements
        html = """
        <html>
            <body>
                <div class="body content-single-wrap">
                    <p>Article content that is long enough to pass validation.</p>
                    <p>Second paragraph to ensure minimum length is met for extraction.</p>
                </div>
            </body>
        </html>
        """
        extractor = JamaicaObserverExtractor()

        # When/Then: extraction raises ValueError for missing title
        with pytest.raises(ValueError, match="Could not extract title"):
            extractor.extract(html, "https://www.jamaicaobserver.com/2026/03/03/test/")

    async def test_missing_body_raises_value_error(self):
        # Given: HTML without article body
        html = """
        <html>
            <body>
                <h1 class="title">Article Title</h1>
            </body>
        </html>
        """
        extractor = JamaicaObserverExtractor()

        # When/Then: extraction raises ValueError for missing body
        with pytest.raises(ValueError, match="Could not find article content container"):
            extractor.extract(html, "https://www.jamaicaobserver.com/2026/03/03/test/")

    async def test_missing_author_returns_none(self):
        # Given: HTML without author elements
        html = """
        <html>
            <body>
                <h1 class="title">Test Title</h1>
                <div class="body content-single-wrap">
                    <p>First paragraph of content that is long enough to pass validation.</p>
                    <p>Second paragraph with more content for the test case here.</p>
                </div>
            </body>
        </html>
        """
        extractor = JamaicaObserverExtractor()

        # When: extracting content
        content = extractor.extract(html, "https://www.jamaicaobserver.com/2026/03/03/test/")

        # Then: author is None (optional field)
        assert content.author is None

    async def test_missing_date_returns_none(self):
        # Given: HTML without date elements
        html = """
        <html>
            <body>
                <h1 class="title">Test Title</h1>
                <div class="body content-single-wrap">
                    <p>First paragraph of content that is long enough to pass validation.</p>
                    <p>Second paragraph with more content for the test case here.</p>
                </div>
            </body>
        </html>
        """
        extractor = JamaicaObserverExtractor()

        # When: extracting content
        content = extractor.extract(html, "https://www.jamaicaobserver.com/2026/03/03/test/")

        # Then: published_date is None (optional field)
        assert content.published_date is None

    async def test_body_fallback_to_article_tag(self):
        # Given: HTML with article.article but no div.body
        html = """
        <html>
            <body>
                <h1 class="title">Test Title</h1>
                <article class="article article_0">
                    <p>First paragraph of content that is long enough to pass validation.</p>
                    <p>Second paragraph with more content to ensure minimum length requirement.</p>
                </article>
            </body>
        </html>
        """
        extractor = JamaicaObserverExtractor()

        # When: extracting content
        content = extractor.extract(html, "https://www.jamaicaobserver.com/2026/03/03/test/")

        # Then: content is extracted from article.article fallback
        assert content.title == "Test Title"
        assert content.full_text.startswith("First paragraph")


class TestJamaicaObserverExtractorAuthorCleaning:
    """Tests for _clean_author_name across the three observed formats."""

    async def test_pipe_delimited_author_with_email_cleaned(self):
        # Given: pipe-delimited format with job title and email
        extractor = JamaicaObserverExtractor()

        # When: cleaning author name
        result = extractor._clean_author_name("Daniel Blake | Sports Writer | blaked@jamaicaobserver.com")

        # Then: only the name remains
        assert result == "Daniel Blake"

    async def test_pipe_delimited_author_without_email_cleaned(self):
        # Given: pipe-delimited format without email
        extractor = JamaicaObserverExtractor()

        # When: cleaning author name
        result = extractor._clean_author_name("Jerome Williams | Reporter")

        # Then: only the name remains
        assert result == "Jerome Williams"

    async def test_by_prefix_with_email_cleaned(self):
        # Given: space-delimited format with "BY" prefix and email
        extractor = JamaicaObserverExtractor()

        # When: cleaning author name
        result = extractor._clean_author_name(
            "BY ALICIA DUNKLEY WILLIS Senior reporter dunkleywillisa@jamaicaobserver.com"
        )

        # Then: "BY " prefix and email removed (job title may remain - known site inconsistency)
        assert "ALICIA DUNKLEY WILLIS" in result
        assert result.startswith("ALICIA")
        assert "BY " not in result
        assert "@" not in result

    async def test_plain_name_unchanged(self):
        # Given: plain author name with no prefixes or suffixes
        extractor = JamaicaObserverExtractor()

        # When: cleaning author name
        result = extractor._clean_author_name("John Smith")

        # Then: name is returned unchanged
        assert result == "John Smith"

    async def test_email_only_author_cleaned_to_empty_string(self):
        # Given: degenerate case with only an email address
        extractor = JamaicaObserverExtractor()

        # When: cleaning
        result = extractor._clean_author_name("reporter@jamaicaobserver.com")

        # Then: result is empty string after email removal
        assert result == ""

    async def test_by_lowercase_prefix_cleaned(self):
        # Given: "by " lowercase prefix
        extractor = JamaicaObserverExtractor()

        # When: cleaning
        result = extractor._clean_author_name("by Jane Doe | Reporter")

        # Then: "by " prefix is not treated as the BY-prefix format (only uppercase "BY " is stripped)
        # The pipe split still cleans up the title
        assert "Jane Doe" in result
