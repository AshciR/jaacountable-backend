"""Tests for domain model validation."""

import pytest

from src.db.models.domain import Article, Classification, NewsSource


class TestArticleValidation:
    """Validation tests for Article model."""

    async def test_empty_url_raises_value_error(self):
        # Given: an article with empty string URL
        # When: Article creation is attempted
        # Then: raises ValueError with message about URL
        with pytest.raises(ValueError, match="URL cannot be empty"):
            Article(
                url="",
                title="Test Article",
                section="news",
                news_source_id=1,
            )

    async def test_whitespace_only_url_raises_value_error(self):
        # Given: an article with whitespace-only URL
        # When: Article creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="URL cannot be empty"):
            Article(
                url="   ",
                title="Test Article",
                section="news",
                news_source_id=1,
            )

    async def test_url_without_protocol_raises_value_error(self):
        # Given: an article with URL missing http:// or https://
        # When: Article creation is attempted
        # Then: raises ValueError with message about URL protocol
        with pytest.raises(ValueError, match="URL must start with http:// or https://"):
            Article(
                url="example.com/article",
                title="Test Article",
                section="news",
                news_source_id=1,
            )

    async def test_empty_title_raises_value_error(self):
        # Given: an article with empty title
        # When: Article creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Article(
                url="https://example.com/article",
                title="",
                section="news",
                news_source_id=1,
            )

    async def test_whitespace_only_title_raises_value_error(self):
        # Given: an article with whitespace-only title
        # When: Article creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Article(
                url="https://example.com/article",
                title="   ",
                section="news",
                news_source_id=1,
            )

    async def test_empty_section_raises_value_error(self):
        # Given: an article with empty section
        # When: Article creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Article(
                url="https://example.com/article",
                title="Test Article",
                section="",
                news_source_id=1,
            )


class TestClassificationValidation:
    """Validation tests for Classification model."""

    async def test_confidence_score_below_zero_raises_value_error(self):
        # Given: a classification with confidence_score < 0
        # When: Classification creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="Confidence score must be between 0.0 and 1.0"):
            Classification(
                article_id=1,
                classifier_type="accountability",
                confidence_score=-0.1,
                model_name="gpt-4o-mini",
            )

    async def test_confidence_score_above_one_raises_value_error(self):
        # Given: a classification with confidence_score > 1
        # When: Classification creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="Confidence score must be between 0.0 and 1.0"):
            Classification(
                article_id=1,
                classifier_type="accountability",
                confidence_score=1.1,
                model_name="gpt-4o-mini",
            )

    async def test_empty_classifier_type_raises_value_error(self):
        # Given: a classification with empty classifier_type
        # When: Classification creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Classification(
                article_id=1,
                classifier_type="",
                confidence_score=0.5,
                model_name="gpt-4o-mini",
            )

    async def test_whitespace_only_classifier_type_raises_value_error(self):
        # Given: a classification with whitespace-only classifier_type
        # When: Classification creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Classification(
                article_id=1,
                classifier_type="   ",
                confidence_score=0.5,
                model_name="gpt-4o-mini",
            )

    async def test_empty_model_name_raises_value_error(self):
        # Given: a classification with empty model_name
        # When: Classification creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Classification(
                article_id=1,
                classifier_type="accountability",
                confidence_score=0.5,
                model_name="",
            )

    async def test_whitespace_only_model_name_raises_value_error(self):
        # Given: a classification with whitespace-only model_name
        # When: Classification creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="Field cannot be empty"):
            Classification(
                article_id=1,
                classifier_type="accountability",
                confidence_score=0.5,
                model_name="   ",
            )


class TestNewsSourceValidation:
    """Validation tests for NewsSource model."""

    async def test_empty_name_raises_value_error(self):
        # Given: a news source with empty string name
        # When: NewsSource creation is attempted
        # Then: raises ValueError with message about field
        with pytest.raises(ValueError, match="Field cannot be empty"):
            NewsSource(
                name="",
                base_url="https://example.com",
            )

    async def test_whitespace_only_name_raises_value_error(self):
        # Given: a news source with whitespace-only name
        # When: NewsSource creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="Field cannot be empty"):
            NewsSource(
                name="   ",
                base_url="https://example.com",
            )

    async def test_empty_base_url_raises_value_error(self):
        # Given: a news source with empty base_url
        # When: NewsSource creation is attempted
        # Then: raises ValueError
        with pytest.raises(ValueError, match="Field cannot be empty"):
            NewsSource(
                name="Test News",
                base_url="",
            )

    async def test_negative_crawl_delay_raises_value_error(self):
        # Given: a news source with negative crawl_delay
        # When: NewsSource creation is attempted
        # Then: raises ValueError with message about crawl_delay
        with pytest.raises(ValueError, match="Crawl delay must be non-negative"):
            NewsSource(
                name="Test News",
                base_url="https://example.com",
                crawl_delay=-5,
            )
