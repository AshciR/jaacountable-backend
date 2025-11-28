"""Shared fixtures for article extractor tests."""
import pytest
from pathlib import Path


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to HTML fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def gleaner_html(fixtures_dir: Path) -> str:
    """Load Gleaner article HTML fixture."""
    return (fixtures_dir / "gleaner_article.html").read_text(encoding="utf-8")
