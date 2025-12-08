"""Shared fixtures for article classification tests."""
from datetime import datetime, timezone

import pytest

from src.article_classification.models import ClassificationInput


@pytest.fixture
def sample_corruption_article() -> ClassificationInput:
    """Sample corruption-related article for testing."""
    return ClassificationInput(
        url="https://jamaica-gleaner.com/article/news/test",
        title="Test Article About OCG Investigation",
        section="news",
        full_text="The Office of the Contractor General has launched an investigation into alleged contract irregularities involving $50 million in procurement contracts at the Ministry of Education.",
        published_date=datetime.now(timezone.utc),
    )
