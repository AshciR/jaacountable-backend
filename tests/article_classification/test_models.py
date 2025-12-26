"""Tests for classification models."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.article_classification.models import (
    ClassificationInput,
    ClassifierType,
    ClassificationResult,
    NormalizedEntity,
)


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


class TestClassifierTypeEnum:
    """Validation tests for ClassifierType enum."""

    async def test_corruption_enum_value_is_uppercase_string(self):
        # Given: ClassifierType.CORRUPTION enum
        # When: accessing its value
        # Then: value is the uppercase string "CORRUPTION"
        assert ClassifierType.CORRUPTION.value == "CORRUPTION"

    async def test_hurricane_relief_enum_value_is_uppercase_string(self):
        # Given: ClassifierType.HURRICANE_RELIEF enum
        # When: accessing its value
        # Then: value is the uppercase string "HURRICANE_RELIEF"
        assert ClassifierType.HURRICANE_RELIEF.value == "HURRICANE_RELIEF"

    async def test_enum_can_be_created_from_string(self):
        # Given: a valid classifier type string
        # When: creating ClassifierType from the string
        # Then: enum instance is created successfully
        corruption = ClassifierType("CORRUPTION")
        hurricane_relief = ClassifierType("HURRICANE_RELIEF")

        assert corruption == ClassifierType.CORRUPTION
        assert hurricane_relief == ClassifierType.HURRICANE_RELIEF

    async def test_enum_serializes_to_string_in_model_dump(self):
        # Given: a ClassificationResult with ClassifierType enum
        # When: dumping the model to dict
        # Then: classifier_type is serialized as string
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Test reasoning",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )

        dumped = result.model_dump()
        assert dumped["classifier_type"] == "CORRUPTION"
        assert isinstance(dumped["classifier_type"], str)

    async def test_enum_values_are_unique(self):
        # Given: ClassifierType enum with multiple values
        # When: comparing the enum values
        # Then: each value is unique
        assert ClassifierType.CORRUPTION != ClassifierType.HURRICANE_RELIEF
        assert ClassifierType.CORRUPTION.value != ClassifierType.HURRICANE_RELIEF.value


class TestClassificationResultValidation:
    """Validation tests for ClassificationResult model."""

    # is_relevant Field Tests

    async def test_is_relevant_true_succeeds(self):
        # Given: a ClassificationResult with is_relevant=True
        # When: creation is attempted
        # Then: ClassificationResult is created successfully
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Article discusses OCG investigation",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.is_relevant is True

    async def test_is_relevant_false_succeeds(self):
        # Given: a ClassificationResult with is_relevant=False
        # When: creation is attempted
        # Then: ClassificationResult is created successfully
        result = ClassificationResult(
            is_relevant=False,
            confidence=0.15,
            reasoning="Article not related to accountability topics",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.is_relevant is False

    # Confidence Validation Tests

    async def test_confidence_below_zero_raises_value_error(self):
        # Given: a ClassificationResult with confidence below 0.0
        # When: creation is attempted
        # Then: raises ValueError with message about confidence range
        with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
            ClassificationResult(
                is_relevant=False,
                confidence=-0.1,
                reasoning="Test reasoning",
                classifier_type=ClassifierType.CORRUPTION,
                model_name="gpt-4o-mini",
            )

    async def test_confidence_above_one_raises_value_error(self):
        # Given: a ClassificationResult with confidence above 1.0
        # When: creation is attempted
        # Then: raises ValueError with message about confidence range
        with pytest.raises(ValueError, match="Confidence must be between 0.0 and 1.0"):
            ClassificationResult(
                is_relevant=True,
                confidence=1.5,
                reasoning="Test reasoning",
                classifier_type=ClassifierType.CORRUPTION,
                model_name="gpt-4o-mini",
            )

    async def test_confidence_at_zero_boundary_succeeds(self):
        # Given: a ClassificationResult with confidence at 0.0
        # When: creation is attempted
        # Then: ClassificationResult is created successfully
        result = ClassificationResult(
            is_relevant=False,
            confidence=0.0,
            reasoning="No relevance detected",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.confidence == 0.0

    async def test_confidence_at_one_boundary_succeeds(self):
        # Given: a ClassificationResult with confidence at 1.0
        # When: creation is attempted
        # Then: ClassificationResult is created successfully
        result = ClassificationResult(
            is_relevant=True,
            confidence=1.0,
            reasoning="Extremely relevant to accountability",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.confidence == 1.0

    async def test_confidence_with_decimal_precision_succeeds(self):
        # Given: a ClassificationResult with high-precision confidence value
        # When: creation is attempted
        # Then: ClassificationResult is created with precision preserved
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.8567,
            reasoning="Highly relevant article",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.confidence == 0.8567

    # Reasoning Validation Tests

    async def test_empty_reasoning_raises_value_error(self):
        # Given: a ClassificationResult with empty reasoning
        # When: creation is attempted
        # Then: raises ValueError with message about empty field
        with pytest.raises(ValueError, match="Field cannot be empty"):
            ClassificationResult(
                is_relevant=True,
                confidence=0.85,
                reasoning="",
                classifier_type=ClassifierType.CORRUPTION,
                model_name="gpt-4o-mini",
            )

    async def test_whitespace_only_reasoning_raises_value_error(self):
        # Given: a ClassificationResult with whitespace-only reasoning
        # When: creation is attempted
        # Then: raises ValueError with message about empty field
        with pytest.raises(ValueError, match="Field cannot be empty"):
            ClassificationResult(
                is_relevant=True,
                confidence=0.85,
                reasoning="   ",
                classifier_type=ClassifierType.CORRUPTION,
                model_name="gpt-4o-mini",
            )

    async def test_reasoning_with_whitespace_is_stripped(self):
        # Given: a ClassificationResult with reasoning having leading/trailing whitespace
        # When: creation is attempted
        # Then: whitespace is stripped and reasoning is valid
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="  Article discusses corruption investigation  ",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.reasoning == "Article discusses corruption investigation"

    async def test_valid_reasoning_succeeds(self):
        # Given: a ClassificationResult with valid long reasoning text
        # When: creation is attempted
        # Then: ClassificationResult is created successfully
        reasoning = "The article discusses the Office of the Contractor General (OCG) investigation into contract irregularities at the Ministry of Education. Multiple officials are implicated in the procurement scandal involving school infrastructure projects worth over $50 million."
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.92,
            reasoning=reasoning,
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.reasoning == reasoning

    # model_name Validation Tests

    async def test_empty_model_name_raises_value_error(self):
        # Given: a ClassificationResult with empty model_name
        # When: creation is attempted
        # Then: raises ValueError with message about empty field
        with pytest.raises(ValueError, match="Field cannot be empty"):
            ClassificationResult(
                is_relevant=True,
                confidence=0.85,
                reasoning="Test reasoning",
                classifier_type=ClassifierType.CORRUPTION,
                model_name="",
            )

    async def test_whitespace_only_model_name_raises_value_error(self):
        # Given: a ClassificationResult with whitespace-only model_name
        # When: creation is attempted
        # Then: raises ValueError with message about empty field
        with pytest.raises(ValueError, match="Field cannot be empty"):
            ClassificationResult(
                is_relevant=True,
                confidence=0.85,
                reasoning="Test reasoning",
                classifier_type=ClassifierType.CORRUPTION,
                model_name="   ",
            )

    async def test_model_name_with_whitespace_is_stripped(self):
        # Given: a ClassificationResult with model_name having leading/trailing whitespace
        # When: creation is attempted
        # Then: whitespace is stripped and model_name is valid
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Test reasoning",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="  gpt-4o-mini  ",
        )
        assert result.model_name == "gpt-4o-mini"

    async def test_valid_model_name_succeeds(self):
        # Given: a ClassificationResult with valid model_name
        # When: creation is attempted
        # Then: ClassificationResult is created successfully
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Test reasoning",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.model_name == "gpt-4o-mini"

    # key_entities Validation Tests

    async def test_key_entities_empty_list_succeeds(self):
        # Given: a ClassificationResult with empty key_entities list (default)
        # When: creation is attempted
        # Then: ClassificationResult is created with empty list
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Test reasoning",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.key_entities == []

    async def test_key_entities_with_valid_items_succeeds(self):
        # Given: a ClassificationResult with valid key_entities list
        # When: creation is attempted
        # Then: ClassificationResult is created with entities preserved
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Test reasoning",
            key_entities=["OCG", "Ministry of Education"],
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.key_entities == ["OCG", "Ministry of Education"]

    async def test_key_entities_strips_whitespace_from_items(self):
        # Given: a ClassificationResult with key_entities having whitespace
        # When: creation is attempted
        # Then: whitespace is stripped from each entity
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Test reasoning",
            key_entities=["  OCG  ", "Ministry of Education  "],
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.key_entities == ["OCG", "Ministry of Education"]

    async def test_key_entities_filters_empty_strings(self):
        # Given: a ClassificationResult with key_entities containing empty strings
        # When: creation is attempted
        # Then: empty strings are filtered out
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Test reasoning",
            key_entities=["OCG", "", "Ministry"],
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.key_entities == ["OCG", "Ministry"]

    async def test_key_entities_filters_whitespace_only_strings(self):
        # Given: a ClassificationResult with key_entities containing whitespace-only strings
        # When: creation is attempted
        # Then: whitespace-only strings are filtered out
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Test reasoning",
            key_entities=["OCG", "   ", "Ministry"],
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.key_entities == ["OCG", "Ministry"]

    async def test_key_entities_with_mixed_valid_and_invalid_items(self):
        # Given: a ClassificationResult with mixed valid and invalid entities
        # When: creation is attempted
        # Then: only valid entities are preserved after cleanup
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Test reasoning",
            key_entities=["  OCG  ", "", "   ", "Ministry"],
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.key_entities == ["OCG", "Ministry"]

    async def test_key_entities_all_empty_becomes_empty_list(self):
        # Given: a ClassificationResult with all empty/whitespace entities
        # When: creation is attempted
        # Then: result has empty list for key_entities
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Test reasoning",
            key_entities=["", "   ", ""],
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.key_entities == []

    # classifier_type Validation Tests

    async def test_classifier_type_corruption_succeeds(self):
        # Given: a ClassificationResult with CORRUPTION classifier_type
        # When: creation is attempted
        # Then: ClassificationResult is created successfully
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Corruption investigation detected",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )
        assert result.classifier_type == ClassifierType.CORRUPTION

    async def test_classifier_type_hurricane_relief_succeeds(self):
        # Given: a ClassificationResult with HURRICANE_RELIEF classifier_type
        # When: creation is attempted
        # Then: ClassificationResult is created successfully
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.88,
            reasoning="Hurricane relief fund management discussed",
            classifier_type=ClassifierType.HURRICANE_RELIEF,
            model_name="gpt-4o-mini",
        )
        assert result.classifier_type == ClassifierType.HURRICANE_RELIEF

    async def test_classifier_type_from_string_succeeds(self):
        # Given: a ClassificationResult with classifier_type as string
        # When: creation is attempted
        # Then: Pydantic converts string to enum successfully
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Test reasoning",
            classifier_type="CORRUPTION",
            model_name="gpt-4o-mini",
        )
        assert result.classifier_type == ClassifierType.CORRUPTION
        assert isinstance(result.classifier_type, ClassifierType)

    async def test_invalid_classifier_type_raises_validation_error(self):
        # Given: a ClassificationResult with invalid classifier_type string
        # When: creation is attempted
        # Then: raises ValidationError from Pydantic
        with pytest.raises(ValidationError):
            ClassificationResult(
                is_relevant=True,
                confidence=0.85,
                reasoning="Test reasoning",
                classifier_type="INVALID_TYPE",
                model_name="gpt-4o-mini",
            )

    # Complete Valid Result Tests

    async def test_valid_result_with_all_fields_succeeds(self):
        # Given: a ClassificationResult with all fields provided and valid
        # When: creation is attempted
        # Then: ClassificationResult is created with all fields correctly set
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.92,
            reasoning="Article discusses OCG investigation into contract irregularities at Ministry of Education",
            key_entities=["OCG", "Ministry of Education", "Contract Irregularities"],
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )

        assert result.is_relevant is True
        assert result.confidence == 0.92
        assert "OCG investigation" in result.reasoning
        assert result.key_entities == ["OCG", "Ministry of Education", "Contract Irregularities"]
        assert result.classifier_type == ClassifierType.CORRUPTION
        assert result.model_name == "gpt-4o-mini"

    async def test_valid_result_with_empty_key_entities_succeeds(self):
        # Given: a ClassificationResult with only required fields
        # When: creation is attempted
        # Then: ClassificationResult is created with key_entities defaulting to []
        result = ClassificationResult(
            is_relevant=False,
            confidence=0.20,
            reasoning="Article not related to accountability topics",
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )

        assert result.is_relevant is False
        assert result.confidence == 0.20
        assert result.key_entities == []
        assert result.classifier_type == ClassifierType.CORRUPTION

    async def test_valid_result_with_corruption_classifier(self):
        # Given: a complete ClassificationResult for CORRUPTION classifier
        # When: creation is attempted
        # Then: ClassificationResult is created successfully with all CORRUPTION-specific details
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.89,
            reasoning="Article details investigation by the Office of the Contractor General into procurement irregularities involving government contracts worth JMD $75 million",
            key_entities=["Office of the Contractor General", "Procurement Irregularities", "Government Contracts"],
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )

        assert result.is_relevant is True
        assert result.classifier_type == ClassifierType.CORRUPTION
        assert "Contractor General" in result.reasoning
        assert "Procurement Irregularities" in result.key_entities

    async def test_valid_result_with_hurricane_relief_classifier(self):
        # Given: a complete ClassificationResult for HURRICANE_RELIEF classifier
        # When: creation is attempted
        # Then: ClassificationResult is created successfully with all HURRICANE_RELIEF-specific details
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.91,
            reasoning="Article examines allocation and management of hurricane relief funds following recent natural disaster, highlighting transparency concerns in distribution process",
            key_entities=["Hurricane Relief Funds", "Fund Allocation", "Transparency Concerns"],
            classifier_type=ClassifierType.HURRICANE_RELIEF,
            model_name="gpt-4o-mini",
        )

        assert result.is_relevant is True
        assert result.classifier_type == ClassifierType.HURRICANE_RELIEF
        assert "hurricane relief funds" in result.reasoning.lower()
        assert "Hurricane Relief Funds" in result.key_entities

    # Edge Cases

    async def test_unicode_in_reasoning_and_key_entities_succeeds(self):
        # Given: a ClassificationResult with Unicode characters (Jamaican names, special chars)
        # When: creation is attempted
        # Then: ClassificationResult is created successfully with Unicode preserved
        result = ClassificationResult(
            is_relevant=True,
            confidence=0.87,
            reasoning="Investigation into Montego Bay development project with €50M budget involving Négril infrastructure",
            key_entities=["Montego Bay", "Négril", "€50M Budget"],
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )

        assert "Négril" in result.reasoning
        assert "€50M" in result.reasoning
        assert "Négril" in result.key_entities
        assert "€50M Budget" in result.key_entities

    async def test_very_long_reasoning_succeeds(self):
        # Given: a ClassificationResult with very long reasoning (1000+ characters)
        # When: creation is attempted
        # Then: ClassificationResult is created successfully with no upper limit issues
        very_long_reasoning = "This is a comprehensive analysis of government accountability. " * 20  # ~1,200 characters

        result = ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning=very_long_reasoning,
            classifier_type=ClassifierType.CORRUPTION,
            model_name="gpt-4o-mini",
        )

        assert len(result.reasoning) > 1000
        # Validator strips whitespace, so compare with stripped version
        assert result.reasoning == very_long_reasoning.strip()


class TestNormalizedEntityValidation:
    """Validation tests for NormalizedEntity model (BDD style)."""

    # Happy path tests

    async def test_valid_normalized_entity_succeeds(self):
        # Given: Valid normalized entity data
        # When: Creating NormalizedEntity
        # Then: Entity is created successfully with all fields
        entity = NormalizedEntity(
            original_value="Hon. Ruel Reid",
            normalized_value="ruel_reid",
            confidence=0.95,
            reason="Removed title 'Hon.' and standardized format",
            context=""
        )

        assert entity.original_value == "Hon. Ruel Reid"
        assert entity.normalized_value == "ruel_reid"
        assert entity.confidence == 0.95
        assert entity.reason == "Removed title 'Hon.' and standardized format"
        assert entity.context == ""

    async def test_normalized_entity_with_context_succeeds(self):
        # Given: Normalized entity with optional context
        # When: Creating NormalizedEntity
        # Then: Entity is created with context preserved
        entity = NormalizedEntity(
            original_value="OCG",
            normalized_value="ocg",
            confidence=1.0,
            reason="Lowercased acronym",
            context="corruption investigation"
        )

        assert entity.context == "corruption investigation"

    async def test_normalized_entity_strips_whitespace(self):
        # Given: Normalized entity with extra whitespace in fields
        # When: Creating NormalizedEntity
        # Then: Whitespace is stripped from string fields
        entity = NormalizedEntity(
            original_value="  Hon. Andrew Holness  ",
            normalized_value="  andrew_holness  ",
            confidence=0.90,
            reason="  Removed title and standardized  ",
            context="  prime minister  "
        )

        assert entity.original_value == "Hon. Andrew Holness"
        assert entity.normalized_value == "andrew_holness"
        assert entity.reason == "Removed title and standardized"
        assert entity.context == "prime minister"

    # Confidence validation tests

    async def test_confidence_at_minimum_succeeds(self):
        # Given: Confidence exactly 0.0
        # When: Creating NormalizedEntity
        # Then: Entity is created successfully
        entity = NormalizedEntity(
            original_value="Test",
            normalized_value="test",
            confidence=0.0,
            reason="Test normalization"
        )

        assert entity.confidence == 0.0

    async def test_confidence_at_maximum_succeeds(self):
        # Given: Confidence exactly 1.0
        # When: Creating NormalizedEntity
        # Then: Entity is created successfully
        entity = NormalizedEntity(
            original_value="OCG",
            normalized_value="ocg",
            confidence=1.0,
            reason="Perfect match"
        )

        assert entity.confidence == 1.0

    async def test_confidence_below_zero_raises_error(self):
        # Given: Confidence below 0.0
        # When: Creating NormalizedEntity
        # Then: ValidationError raised
        with pytest.raises(ValidationError):
            NormalizedEntity(
                original_value="Test",
                normalized_value="test",
                confidence=-0.1,
                reason="test"
            )

    async def test_confidence_above_one_raises_error(self):
        # Given: Confidence above 1.0
        # When: Creating NormalizedEntity
        # Then: ValidationError raised
        with pytest.raises(ValidationError):
            NormalizedEntity(
                original_value="Test",
                normalized_value="test",
                confidence=1.1,
                reason="test"
            )

    # Empty field validation tests

    async def test_empty_original_value_raises_error(self):
        # Given: Empty original_value
        # When: Creating NormalizedEntity
        # Then: ValidationError raised
        with pytest.raises(ValidationError, match="Field cannot be empty"):
            NormalizedEntity(
                original_value="",
                normalized_value="test",
                confidence=0.9,
                reason="test"
            )

    async def test_whitespace_only_original_value_raises_error(self):
        # Given: Whitespace-only original_value
        # When: Creating NormalizedEntity
        # Then: ValidationError raised
        with pytest.raises(ValidationError, match="Field cannot be empty"):
            NormalizedEntity(
                original_value="   ",
                normalized_value="test",
                confidence=0.9,
                reason="test"
            )

    async def test_empty_normalized_value_raises_error(self):
        # Given: Empty normalized_value
        # When: Creating NormalizedEntity
        # Then: ValidationError raised
        with pytest.raises(ValidationError, match="Field cannot be empty"):
            NormalizedEntity(
                original_value="Test",
                normalized_value="",
                confidence=0.9,
                reason="test"
            )

    async def test_whitespace_only_normalized_value_raises_error(self):
        # Given: Whitespace-only normalized_value
        # When: Creating NormalizedEntity
        # Then: ValidationError raised
        with pytest.raises(ValidationError, match="Field cannot be empty"):
            NormalizedEntity(
                original_value="Test",
                normalized_value="   ",
                confidence=0.9,
                reason="test"
            )

    async def test_empty_reason_raises_error(self):
        # Given: Empty reason
        # When: Creating NormalizedEntity
        # Then: ValidationError raised
        with pytest.raises(ValidationError, match="Field cannot be empty"):
            NormalizedEntity(
                original_value="Test",
                normalized_value="test",
                confidence=0.9,
                reason=""
            )

    async def test_whitespace_only_reason_raises_error(self):
        # Given: Whitespace-only reason
        # When: Creating NormalizedEntity
        # Then: ValidationError raised
        with pytest.raises(ValidationError, match="Field cannot be empty"):
            NormalizedEntity(
                original_value="Test",
                normalized_value="test",
                confidence=0.9,
                reason="   "
            )

    async def test_empty_context_succeeds(self):
        # Given: Empty context (optional field)
        # When: Creating NormalizedEntity
        # Then: Entity is created successfully with empty context
        entity = NormalizedEntity(
            original_value="Test",
            normalized_value="test",
            confidence=0.9,
            reason="test normalization",
            context=""
        )

        assert entity.context == ""

    async def test_missing_context_uses_default(self):
        # Given: NormalizedEntity without context parameter
        # When: Creating NormalizedEntity
        # Then: Context defaults to empty string
        entity = NormalizedEntity(
            original_value="Test",
            normalized_value="test",
            confidence=0.9,
            reason="test normalization"
        )

        assert entity.context == ""

    # Edge case tests

    async def test_unicode_entities_preserved(self):
        # Given: Entity with Unicode characters
        # When: Creating NormalizedEntity
        # Then: Unicode is preserved in both original and normalized
        entity = NormalizedEntity(
            original_value="Négril Tourism Board",
            normalized_value="négril_tourism_board",
            confidence=0.85,
            reason="Preserved diacritics",
            context="tourism"
        )

        assert "Négril" in entity.original_value
        assert "négril" in entity.normalized_value

    async def test_very_long_entity_names_succeed(self):
        # Given: Very long entity names (200+ characters)
        # When: Creating NormalizedEntity
        # Then: Entity is created successfully with no length limits
        long_original = "The Ministry of Tourism and Entertainment of Jamaica and the Caribbean Region " * 3  # ~240 chars
        long_normalized = "ministry_of_tourism_and_entertainment_of_jamaica_and_the_caribbean_region"

        entity = NormalizedEntity(
            original_value=long_original,
            normalized_value=long_normalized,
            confidence=0.75,
            reason="Very long entity name standardized"
        )

        assert len(entity.original_value) > 200
        assert entity.original_value == long_original.strip()

    async def test_very_long_reason_succeeds(self):
        # Given: Very long reason (500+ characters)
        # When: Creating NormalizedEntity
        # Then: Entity is created successfully
        long_reason = "Applied comprehensive normalization rules including title removal, case standardization, space replacement, and entity type classification. " * 5  # ~700 chars

        entity = NormalizedEntity(
            original_value="Test",
            normalized_value="test",
            confidence=0.9,
            reason=long_reason
        )

        assert len(entity.reason) > 500
        assert entity.reason == long_reason.strip()
