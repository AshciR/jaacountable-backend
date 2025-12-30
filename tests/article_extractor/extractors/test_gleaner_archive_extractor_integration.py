from datetime import datetime, timezone

import pytest

from src.article_extractor.extractors.gleaner_archive_extractor import GleanerArchiveExtractor
from src.article_extractor.models import ExtractedArticleContent


class TestGleanerArchiveExtractorIntegration:
    """Integration tests for archive article extraction."""

    @pytest.mark.external
    @pytest.mark.integration
    async def test_extract_real_archive_page(self, gleaner_archive_html: str):
        # Given: real archive page HTML from gleaner.newspaperarchive.com
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