"""Tests for GleanerArchiveExtractor (newspaper archive OCR extraction)."""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from src.article_extractor.extractors.gleaner_archive_extractor import GleanerArchiveExtractor
from src.article_extractor.models import ExtractedArticleContent


class TestGleanerArchiveExtractorHappyPath:
    """Happy path tests for archive article extraction."""

    @patch("src.article_extractor.extractors.gleaner_archive_extractor.completion")
    async def test_extract_real_archive_page(self, mock_completion, gleaner_archive_html: str):
        # Given: real archive page HTML from gleaner.newspaperarchive.com
        # Mock LLM responses for title and author extraction
        mock_completion.side_effect = [
            # First call: headline extraction (returns NONE - no headline found)
            Mock(choices=[Mock(message=Mock(content="NONE"))]),
            # Second call: author extraction (returns Livern Barrett)
            Mock(choices=[Mock(message=Mock(content="Livern Barrett"))]),
        ]

        extractor = GleanerArchiveExtractor()
        url = "https://gleaner.newspaperarchive.com/kingston-gleaner/2021-11-07/page-5/"

        # When: extracting content
        content = extractor.extract(gleaner_archive_html, url)

        # Then: extraction succeeds with valid data
        assert isinstance(content, ExtractedArticleContent)

        # Title should be extracted (from og:title or h1)
        assert content.title is not None
        assert len(content.title) > 0

        # Full text should be extracted from OCR section
        assert content.full_text is not None
        assert len(content.full_text) >= 50
        # This article is about Ruel Reid and CMU fraud case
        assert "Reid" in content.full_text or "CMU" in content.full_text

        # Date should be extracted from URL (2021-11-07)
        assert content.published_date is not None
        assert content.published_date == datetime(2021, 11, 7, tzinfo=timezone.utc)

        # Author should be extracted by LLM
        assert content.author == "Livern Barrett"

    @patch("src.article_extractor.extractors.gleaner_archive_extractor.completion")
    async def test_extract_page_with_multiple_articles(
        self, mock_completion, gleaner_archive_page_with_multiple_articles: str
    ):
        # Given: archive page with multiple articles (HEART article + congratulations)
        # Mock LLM responses for title and author extraction
        mock_completion.side_effect = [
            # First call: headline extraction (returns NONE - no headline found)
            Mock(choices=[Mock(message=Mock(content="NONE"))]),
            # Second call: author extraction (returns Jovan Johnson from main article)
            Mock(choices=[Mock(message=Mock(content="Jovan Johnson"))]),
        ]

        extractor = GleanerArchiveExtractor()
        url = "https://gleaner.newspaperarchive.com/kingston-gleaner/2021-11-07/page-3/"

        # When: extracting content
        content = extractor.extract(gleaner_archive_page_with_multiple_articles, url)

        # Then: extraction succeeds with data from main article
        assert isinstance(content, ExtractedArticleContent)

        # Title should follow the archive page format (from og:title)
        assert content.title == "Kingston Gleaner Newspaper Archives | Nov 07, 2021, p. 3"

        # Full text should include all OCR content (both articles)
        assert content.full_text is not None
        assert len(content.full_text) >= 50
        # Should contain main HEART article
        assert "HEART" in content.full_text or "Jovan Johnson" in content.full_text
        # Should also contain congratulations message (all OCR text)
        assert "Congratulations" in content.full_text

        # Author should be from main article (Jovan Johnson), not from congratulations
        # LLM should extract author from beginning of text (where main article is)
        assert content.author is not None
        # Author should be Jovan Johnson (from main HEART article)
        assert "Jovan" in content.author or "Johnson" in content.author

        # Date should be extracted from URL
        assert content.published_date is not None
        assert content.published_date == datetime(2021, 11, 7, tzinfo=timezone.utc)
