"""Tests for ExtractedArticleContent model validation and normalization."""
import pytest

from src.article_extractor.models import ExtractedArticleContent

FULL_TEXT_MIN = "x" * 50


class TestExtractedArticleContentTitleNormalization:
    """Tests for HTML entity decoding in article titles."""

    async def test_title_curly_quotes_decoded(self):
        # Given: title with HTML curly quote entities (the exact bug report example)
        raw_title = "St Thomas Eastern MP calls for NWA to address &#8216;ongoing flooding&#8217; in Port Morant"

        # When: creating ExtractedArticleContent
        content = ExtractedArticleContent(title=raw_title, full_text=FULL_TEXT_MIN)

        # Then: entities are decoded to Unicode curly quotes
        assert content.title == "St Thomas Eastern MP calls for NWA to address \u2018ongoing flooding\u2019 in Port Morant"

    async def test_title_amp_entity_decoded(self):
        # Given: title with &amp; entity
        # When / Then
        content = ExtractedArticleContent(title="Roads &amp; Infrastructure Ministry", full_text=FULL_TEXT_MIN)
        assert content.title == "Roads & Infrastructure Ministry"

    async def test_title_quot_entity_decoded(self):
        # Given: title with &quot; entity
        content = ExtractedArticleContent(title='PM says &quot;no tolerance&quot; for corruption', full_text=FULL_TEXT_MIN)
        assert content.title == 'PM says "no tolerance" for corruption'

    async def test_title_ellipsis_entity_decoded(self):
        # Given: title with &#8230; (ellipsis) entity
        content = ExtractedArticleContent(title="MPs debate budget&#8230; again", full_text=FULL_TEXT_MIN)
        assert content.title == "MPs debate budget\u2026 again"

    async def test_title_angle_brackets_decoded(self):
        # Given: title with &lt; / &gt; entities
        content = ExtractedArticleContent(title="Scores &lt; 50 flagged for review", full_text=FULL_TEXT_MIN)
        assert content.title == "Scores < 50 flagged for review"

    async def test_title_with_no_entities_passes_through_unchanged(self):
        # Given: a plain title with no HTML entities
        plain = "St Thomas Eastern MP calls for action"
        content = ExtractedArticleContent(title=plain, full_text=FULL_TEXT_MIN)
        assert content.title == plain

    async def test_title_already_decoded_unicode_unchanged(self):
        # Given: title that already contains the decoded Unicode characters (idempotency)
        decoded = "MP calls for \u2018accountability\u2019 in spending"
        content = ExtractedArticleContent(title=decoded, full_text=FULL_TEXT_MIN)
        assert content.title == decoded

    async def test_title_mixed_entities_and_plain_text(self):
        # Given: title mixing HTML entities and regular text
        content = ExtractedArticleContent(
            title="Gov&#8217;t &amp; Opposition clash over &#8216;secret&#8217; report",
            full_text=FULL_TEXT_MIN,
        )
        assert content.title == "Gov\u2019t & Opposition clash over \u2018secret\u2019 report"

    async def test_title_stripping_still_applied_after_decode(self):
        # Given: title with leading/trailing whitespace around entities
        content = ExtractedArticleContent(
            title="  &#8216;Breaking News&#8217;  ",
            full_text=FULL_TEXT_MIN,
        )
        assert content.title == "\u2018Breaking News\u2019"
