"""Tests for classification models."""

import pytest
from datetime import datetime, timezone

from src.services.article_classification.models import ClassificationInput


class TestClassificationInputValidation:
    """Validation tests for ClassificationInput model."""

    # URL validation tests

    async def test_empty_url_raises_value_error(self):
        # Given: a ClassificationInput with empty URL
        # When: creation is attempted
        # Then: raises ValueError with message about URL
        with pytest.raises(ValueError, match="URL cannot be empty"):
            ClassificationInput(
                url="",
                title="Test Title",
                section="News",
                full_text="A" * 60,
            )

    async def test_whitespace_only_url_raises_value_error(self):
        # Given: a ClassificationInput with whitespace-only URL
        # When: creation is attempted
        # Then: raises ValueError with message about URL
        with pytest.raises(ValueError, match="URL cannot be empty"):
            ClassificationInput(
                url="   ",
                title="Test Title",
                section="News",
                full_text="A" * 60,
            )

    async def test_url_without_protocol_raises_value_error(self):
        # Given: a ClassificationInput with URL missing http:// or https://
        # When: creation is attempted
        # Then: raises ValueError with message about URL protocol
        with pytest.raises(ValueError, match="URL must start with http:// or https://"):
            ClassificationInput(
                url="example.com/article",
                title="Test Title",
                section="News",
                full_text="A" * 60,
            )

    async def test_url_with_leading_trailing_whitespace_is_stripped(self):
        # Given: a ClassificationInput with URL having leading/trailing whitespace
        # When: creation is attempted
        # Then: whitespace is stripped and URL is valid
        input_data = ClassificationInput(
            url="  https://example.com/article  ",
            title="Test Title",
            section="News",
            full_text="A" * 60,
        )
        assert input_data.url == "https://example.com/article"

    async def test_valid_url_with_https_succeeds(self):
        # Given: a ClassificationInput with valid HTTPS URL
        # When: creation is attempted
        # Then: ClassificationInput is created successfully
        input_data = ClassificationInput(
            url="https://jamaica-gleaner.com/article/news/test",
            title="Test Title",
            section="News",
            full_text="A" * 60,
        )
        assert input_data.url == "https://jamaica-gleaner.com/article/news/test"

    # Title validation tests

    async def test_empty_title_raises_value_error(self):
        # Given: a ClassificationInput with empty title
        # When: creation is attempted
        # Then: raises ValueError with message about empty field
        with pytest.raises(ValueError, match="Field cannot be empty"):
            ClassificationInput(
                url="https://example.com/article",
                title="",
                section="News",
                full_text="A" * 60,
            )

    async def test_whitespace_only_title_raises_value_error(self):
        # Given: a ClassificationInput with whitespace-only title
        # When: creation is attempted
        # Then: raises ValueError with message about empty field
        with pytest.raises(ValueError, match="Field cannot be empty"):
            ClassificationInput(
                url="https://example.com/article",
                title="   ",
                section="News",
                full_text="A" * 60,
            )

    async def test_title_with_leading_trailing_whitespace_is_stripped(self):
        # Given: a ClassificationInput with title having leading/trailing whitespace
        # When: creation is attempted
        # Then: whitespace is stripped and title is valid
        input_data = ClassificationInput(
            url="https://example.com/article",
            title="  Test Title  ",
            section="News",
            full_text="A" * 60,
        )
        assert input_data.title == "Test Title"

    async def test_valid_title_succeeds(self):
        # Given: a ClassificationInput with valid title
        # When: creation is attempted
        # Then: ClassificationInput is created successfully
        input_data = ClassificationInput(
            url="https://example.com/article",
            title="Government Announces New Transparency Measures",
            section="News",
            full_text="A" * 60,
        )
        assert input_data.title == "Government Announces New Transparency Measures"

    # Section validation tests

    async def test_empty_section_raises_value_error(self):
        # Given: a ClassificationInput with empty section
        # When: creation is attempted
        # Then: raises ValueError with message about empty field
        with pytest.raises(ValueError, match="Field cannot be empty"):
            ClassificationInput(
                url="https://example.com/article",
                title="Test Title",
                section="",
                full_text="A" * 60,
            )

    async def test_whitespace_only_section_raises_value_error(self):
        # Given: a ClassificationInput with whitespace-only section
        # When: creation is attempted
        # Then: raises ValueError with message about empty field
        with pytest.raises(ValueError, match="Field cannot be empty"):
            ClassificationInput(
                url="https://example.com/article",
                title="Test Title",
                section="   ",
                full_text="A" * 60,
            )

    async def test_section_with_leading_trailing_whitespace_is_stripped(self):
        # Given: a ClassificationInput with section having leading/trailing whitespace
        # When: creation is attempted
        # Then: whitespace is stripped and section is valid
        input_data = ClassificationInput(
            url="https://example.com/article",
            title="Test Title",
            section="  Politics  ",
            full_text="A" * 60,
        )
        assert input_data.section == "Politics"

    async def test_valid_section_succeeds(self):
        # Given: a ClassificationInput with valid section
        # When: creation is attempted
        # Then: ClassificationInput is created successfully
        input_data = ClassificationInput(
            url="https://example.com/article",
            title="Test Title",
            section="Lead Stories",
            full_text="A" * 60,
        )
        assert input_data.section == "Lead Stories"

    # Full text validation tests

    async def test_empty_full_text_raises_value_error(self):
        # Given: a ClassificationInput with empty full_text
        # When: creation is attempted
        # Then: raises ValueError with message about empty full text
        with pytest.raises(ValueError, match="Full text cannot be empty"):
            ClassificationInput(
                url="https://example.com/article",
                title="Test Title",
                section="News",
                full_text="",
            )

    async def test_whitespace_only_full_text_raises_value_error(self):
        # Given: a ClassificationInput with whitespace-only full_text
        # When: creation is attempted
        # Then: raises ValueError with message about empty full text
        with pytest.raises(ValueError, match="Full text cannot be empty"):
            ClassificationInput(
                url="https://example.com/article",
                title="Test Title",
                section="News",
                full_text="   ",
            )

    async def test_full_text_below_minimum_length_raises_value_error(self):
        # Given: a ClassificationInput with full_text below 50 characters
        # When: creation is attempted
        # Then: raises ValueError with message about minimum length
        with pytest.raises(ValueError, match="Full text must be at least 50 characters"):
            ClassificationInput(
                url="https://example.com/article",
                title="Test Title",
                section="News",
                full_text="Short text with only 49 chars in this string",  # 45 chars
            )

    async def test_full_text_at_minimum_length_succeeds(self):
        # Given: a ClassificationInput with full_text at exactly 50 characters
        # When: creation is attempted
        # Then: ClassificationInput is created successfully
        text_50_chars = "A" * 50
        input_data = ClassificationInput(
            url="https://example.com/article",
            title="Test Title",
            section="News",
            full_text=text_50_chars,
        )
        assert len(input_data.full_text) == 50

    async def test_full_text_with_leading_trailing_whitespace_is_stripped(self):
        # Given: a ClassificationInput with full_text having leading/trailing whitespace
        # When: creation is attempted
        # Then: whitespace is stripped and length is validated on stripped text
        text_60_chars = "B" * 60
        input_data = ClassificationInput(
            url="https://example.com/article",
            title="Test Title",
            section="News",
            full_text=f"  {text_60_chars}  ",
        )
        assert len(input_data.full_text) == 60
        assert input_data.full_text == text_60_chars

    # Published date validation tests

    async def test_published_date_without_timezone_raises_value_error(self):
        # Given: a ClassificationInput with naive datetime (no timezone)
        # When: creation is attempted
        # Then: raises ValueError with message about timezone
        with pytest.raises(ValueError, match="Published date must be timezone-aware"):
            ClassificationInput(
                url="https://example.com/article",
                title="Test Title",
                section="News",
                full_text="A" * 60,
                published_date=datetime(2025, 12, 1, 10, 0, 0),  # No timezone
            )

    async def test_published_date_with_timezone_succeeds(self):
        # Given: a ClassificationInput with timezone-aware datetime
        # When: creation is attempted
        # Then: ClassificationInput is created successfully
        pub_date = datetime(2025, 12, 1, 10, 0, 0, tzinfo=timezone.utc)
        input_data = ClassificationInput(
            url="https://example.com/article",
            title="Test Title",
            section="News",
            full_text="A" * 60,
            published_date=pub_date,
        )
        assert input_data.published_date == pub_date

    async def test_published_date_none_succeeds(self):
        # Given: a ClassificationInput without published_date (None)
        # When: creation is attempted
        # Then: ClassificationInput is created successfully with None
        input_data = ClassificationInput(
            url="https://example.com/article",
            title="Test Title",
            section="News",
            full_text="A" * 60,
        )
        assert input_data.published_date is None

    # Complete valid input tests

    async def test_valid_input_with_all_fields_succeeds(self):
        # Given: a ClassificationInput with all fields provided and valid
        # When: creation is attempted
        # Then: ClassificationInput is created with all fields correctly set
        url = "https://jamaica-gleaner.com/article/news/20251201/example"
        title = "Government Announces Transparency Initiative"
        section = "Politics"
        full_text = "The Ministry of Finance today announced a comprehensive transparency initiative aimed at improving accountability in government procurement processes. The new measures will require all contracts above $1 million to be publicly disclosed within 30 days of award."
        pub_date = datetime(2025, 12, 1, 14, 30, 0, tzinfo=timezone.utc)

        input_data = ClassificationInput(
            url=url,
            title=title,
            section=section,
            full_text=full_text,
            published_date=pub_date,
        )

        assert input_data.url == url
        assert input_data.title == title
        assert input_data.section == section
        assert input_data.full_text == full_text
        assert input_data.published_date == pub_date

    async def test_valid_input_without_optional_published_date_succeeds(self):
        # Given: a ClassificationInput with only required fields
        # When: creation is attempted
        # Then: ClassificationInput is created with published_date as None
        url = "https://jamaica-gleaner.com/article/news/example"
        title = "Breaking News Story"
        section = "News"
        full_text = "A" * 100

        input_data = ClassificationInput(
            url=url,
            title=title,
            section=section,
            full_text=full_text,
        )

        assert input_data.url == url
        assert input_data.title == title
        assert input_data.section == section
        assert input_data.full_text == full_text
        assert input_data.published_date is None

    # Edge case tests

    async def test_unicode_in_title_and_full_text_succeeds(self):
        # Given: a ClassificationInput with Unicode characters (Jamaican place names)
        # When: creation is attempted
        # Then: ClassificationInput is created successfully with Unicode preserved
        title = "Development Project in Montego Bay and Négril Announced"
        full_text = "The Prime Minister announced a major development project spanning Montego Bay, Négril, and Ocho Ríos. The €50 million initiative will focus on sustainable tourism infrastructure."

        input_data = ClassificationInput(
            url="https://jamaica-gleaner.com/article/news/example",
            title=title,
            section="News",
            full_text=full_text,
        )

        assert input_data.title == title
        assert input_data.full_text == full_text
        assert "Négril" in input_data.title
        assert "Ocho Ríos" in input_data.full_text
        assert "€" in input_data.full_text

    async def test_very_long_full_text_succeeds(self):
        # Given: a ClassificationInput with very long full_text (10,000 characters)
        # When: creation is attempted
        # Then: ClassificationInput is created successfully with no upper limit issues
        very_long_text = "This is a very long article. " * 350  # ~10,150 characters

        input_data = ClassificationInput(
            url="https://jamaica-gleaner.com/article/news/example",
            title="Comprehensive Analysis of Government Policy",
            section="News",
            full_text=very_long_text,
        )

        assert len(input_data.full_text) > 10000
        # Validator strips whitespace, so compare with stripped version
        assert input_data.full_text == very_long_text.strip()
