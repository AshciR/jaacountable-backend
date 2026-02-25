"""Shared fixtures for article discovery tests."""

import pytest
from pathlib import Path


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to HTML fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def archive_page_nov_07_page_1(fixtures_dir: Path) -> str:
    """Load Nov 07 archive page 1 with next link to page 2."""
    return (fixtures_dir / "archive_page_nov_07_page_1.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_nov_07_page_2(fixtures_dir: Path) -> str:
    """Load Nov 07 archive page 2 with prev link to page 1 and next link to page 3."""
    return (fixtures_dir / "archive_page_nov_07_page_2.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_nov_07_page_3(fixtures_dir: Path) -> str:
    """Load Nov 07 archive page 3 with prev link to page 2 and next link to page 4."""
    return (fixtures_dir / "archive_page_nov_07_page_3.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_nov_07_page_4(fixtures_dir: Path) -> str:
    """Load Nov 07 archive page 4 (last page) with prev link to page 3."""
    return (fixtures_dir / "archive_page_nov_07_page_4.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_no_og_title(fixtures_dir: Path) -> str:
    """Load archive page without og:title (only title tag)."""
    return (fixtures_dir / "archive_page_no_og_title.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_no_title(fixtures_dir: Path) -> str:
    """Load archive page with no title tags."""
    return (fixtures_dir / "archive_page_no_title.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_malformed(fixtures_dir: Path) -> str:
    """Load malformed archive page HTML."""
    return (fixtures_dir / "archive_page_malformed.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_nov_06(fixtures_dir: Path) -> str:
    """Load archive page for November 6, 2021 (single page)."""
    return (fixtures_dir / "archive_page_nov_06.html").read_text(encoding="utf-8")


@pytest.fixture
def archive_page_nov_05(fixtures_dir: Path) -> str:
    """Load archive page for November 5, 2021 (single page)."""
    return (fixtures_dir / "archive_page_nov_05.html").read_text(encoding="utf-8")


# ── Jamaica Observer archive fixtures ────────────────────────────────────────


@pytest.fixture
def jo_archive_page_with_articles(fixtures_dir: Path) -> str:
    """Sep 15 archive: 2 News articles, 1 Sports, 1 Entertainment, 1 International News, 1 sidebar."""
    return (fixtures_dir / "jo_archive_page_with_articles.html").read_text(encoding="utf-8")


@pytest.fixture
def jo_archive_page_empty(fixtures_dir: Path) -> str:
    """Sep 21 archive: valid page but no News category_main articles."""
    return (fixtures_dir / "jo_archive_page_empty.html").read_text(encoding="utf-8")


@pytest.fixture
def jo_archive_page_with_pagination(fixtures_dir: Path) -> str:
    """Sep 20 archive page 1: 2 News articles with <link rel='next'>."""
    return (fixtures_dir / "jo_archive_page_with_pagination.html").read_text(encoding="utf-8")


@pytest.fixture
def jo_archive_page_2(fixtures_dir: Path) -> str:
    """Sep 20 archive page 2: 1 News article, no next link."""
    return (fixtures_dir / "jo_archive_page_2.html").read_text(encoding="utf-8")


# ── Jamaica Observer sitemap fixtures ────────────────────────────────────────


@pytest.fixture
def jo_sitemap_index(fixtures_dir: Path) -> str:
    """Sitemap index with page-sitemap, old/new sitemaps, and 2 in-range post-sitemaps."""
    return (fixtures_dir / "jo_sitemap_index.xml").read_text(encoding="utf-8")


@pytest.fixture
def jo_post_sitemap_in_range(fixtures_dir: Path) -> str:
    """Post-sitemap with 3 article URLs all within June 2020 target range."""
    return (fixtures_dir / "jo_post_sitemap_in_range.xml").read_text(encoding="utf-8")


@pytest.fixture
def jo_post_sitemap_mixed(fixtures_dir: Path) -> str:
    """Post-sitemap with 4 URLs: 2 in June 2020 range, 1 before, 1 after."""
    return (fixtures_dir / "jo_post_sitemap_mixed.xml").read_text(encoding="utf-8")
