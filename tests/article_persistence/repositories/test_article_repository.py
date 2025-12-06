"""Tests for ArticleRepository."""

import asyncpg
import pytest
from datetime import datetime, timedelta, timezone

from src.article_persistence.repositories.article_repository import ArticleRepository
from src.article_persistence.models.domain import Article
from tests.article_persistence.repositories.utils import create_test_news_source


class TestInsertArticleHappyPath:
    """Happy path tests for insert_article."""

    async def test_insert_article_success(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a valid article with all fields populated
        article = Article(
            url="https://example.com/test-article",
            title="Test Article",
            section="news",
            published_date=datetime(2025, 11, 15, tzinfo=timezone.utc),
            full_text="Article content here",
            news_source_id=1,
        )
        repository = ArticleRepository()

        # When: the article is inserted
        result = await repository.insert_article(db_connection, article)

        # Then: the returned article has a database-generated id and matching fields
        assert result.id is not None
        assert result.url == article.url
        assert result.title == article.title
        assert result.section == article.section
        assert result.published_date == article.published_date
        assert result.full_text == article.full_text
        assert result.news_source_id == 1

    async def test_insert_article_with_minimal_fields(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article with only required fields (url, title, section)
        article = Article(
            url="https://example.com/minimal-article",
            title="Minimal Article",
            section="lead-stories",
            news_source_id=1,
        )
        repository = ArticleRepository()

        # When: the article is inserted
        result = await repository.insert_article(db_connection, article)

        # Then: returns article with id, defaults applied, optional fields are None
        assert result.id is not None
        assert result.url == article.url
        assert result.title == article.title
        assert result.section == article.section
        assert result.published_date is None
        assert result.full_text is None
        assert result.fetched_at is not None


    async def test_insert_article_preserves_full_text_in_return(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article with full_text content
        full_text_content = "This is the complete article text that should be preserved."
        article = Article(
            url="https://example.com/preserve-full-text",
            title="Full Text Preservation Test",
            section="news",
            full_text=full_text_content,
            news_source_id=1,
        )
        repository = ArticleRepository()

        # When: the article is inserted
        result = await repository.insert_article(db_connection, article)

        # Then: returns article includes the original full_text
        # (verifies repository preserves it since SQL doesn't return it)
        assert result.full_text == full_text_content

    async def test_insert_article_with_http_url(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article with http:// URL (not https)
        article = Article(
            url="http://example.com/http-article",
            title="HTTP URL Article",
            section="news",
            news_source_id=1,
        )
        repository = ArticleRepository()

        # When: the article is inserted
        result = await repository.insert_article(db_connection, article)

        # Then: returns article successfully (validates http:// is accepted)
        assert result.id is not None
        assert result.url == "http://example.com/http-article"

    async def test_insert_article_strips_whitespace(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article with whitespace-padded fields
        article = Article(
            url="  https://example.com/whitespace-test  ",
            title="  Whitespace Title  ",
            section="  news  ",
            news_source_id=1,
        )
        repository = ArticleRepository()

        # When: the article is inserted
        result = await repository.insert_article(db_connection, article)

        # Then: returns article with trimmed fields (Pydantic validation)
        assert result.id is not None
        assert result.url == "https://example.com/whitespace-test"
        assert result.title == "Whitespace Title"
        assert result.section == "news"

    async def test_insert_multiple_articles_sequential(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: multiple valid articles with different URLs
        repository = ArticleRepository()
        articles = [
            Article(
                url=f"https://example.com/article-{i}",
                title=f"Article {i}",
                section="news",
                news_source_id=1,
            )
            for i in range(3)
        ]

        # When: each article is inserted sequentially
        results = []
        for article in articles:
            result = await repository.insert_article(db_connection, article)
            results.append(result)

        # Then: each gets unique auto-incrementing id
        ids = [r.id for r in results]
        assert len(set(ids)) == 3  # All IDs are unique
        assert all(id is not None for id in ids)


class TestInsertArticleDatabaseConstraints:
    """Database constraint tests for insert_article."""

    async def test_cannot_delete_news_source_with_articles(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: a news source exists with an article referencing it
        news_source = await create_test_news_source(
            conn=db_connection,
            name="News Source With Articles",
        )
        repository = ArticleRepository()
        article = Article(
            url="https://example.com/restrict-test",
            title="Article Referencing News Source",
            section="news",
            news_source_id=news_source.id,
        )
        await repository.insert_article(db_connection, article)

        # When: attempting to delete the news source
        # Then: raises RestrictViolationError due to ON DELETE RESTRICT
        with pytest.raises(asyncpg.RestrictViolationError):
            await db_connection.execute(
                "DELETE FROM news_sources WHERE id = $1",
                news_source.id,
            )

    async def test_duplicate_url_raises_unique_violation(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article already exists with a specific URL
        repository = ArticleRepository()
        first_article = Article(
            url="https://example.com/duplicate-test",
            title="First Article",
            section="news",
            news_source_id=1,
        )
        await repository.insert_article(db_connection, first_article)

        # When: another article with the same URL is inserted
        second_article = Article(
            url="https://example.com/duplicate-test",
            title="Second Article",
            section="lead-stories",
            news_source_id=1,
        )

        # Then: raises asyncpg.UniqueViolationError
        with pytest.raises(asyncpg.UniqueViolationError):
            await repository.insert_article(db_connection, second_article)

    async def test_same_url_different_section_fails(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article exists with URL X
        repository = ArticleRepository()
        first_article = Article(
            url="https://example.com/url-unique-test",
            title="News Article",
            section="news",
            news_source_id=1,
        )
        await repository.insert_article(db_connection, first_article)

        # When: another article with same URL X but different section is inserted
        second_article = Article(
            url="https://example.com/url-unique-test",
            title="Lead Story Article",
            section="lead-stories",
            news_source_id=1,
        )

        # Then: raises UniqueViolationError (URL uniqueness is global, not per-section)
        with pytest.raises(asyncpg.UniqueViolationError):
            await repository.insert_article(db_connection, second_article)


class TestInsertArticleEdgeCases:
    """Edge case tests for insert_article."""

    async def test_with_special_characters_in_url(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article with URL containing query params, fragments, encoded characters
        special_url = "https://example.com/article?param=value&other=123#section-1"
        article = Article(
            url=special_url,
            title="Special URL Article",
            section="news",
            news_source_id=1,
        )
        repository = ArticleRepository()

        # When: the article is inserted
        result = await repository.insert_article(db_connection, article)

        # Then: returns article with URL preserved correctly
        assert result.id is not None
        assert result.url == special_url

    async def test_with_unicode_title(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article with Unicode characters in title (accents, special chars)
        unicode_title = "Café Culture: Jamaica's Growing Artisanal Scene — 日本語テスト"
        article = Article(
            url="https://example.com/unicode-title",
            title=unicode_title,
            section="news",
            news_source_id=1,
        )
        repository = ArticleRepository()

        # When: the article is inserted
        result = await repository.insert_article(db_connection, article)

        # Then: returns article with Unicode title preserved
        assert result.id is not None
        assert result.title == unicode_title

    async def test_with_very_long_full_text(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article with very long full_text (100KB of text)
        long_text = "This is a test paragraph. " * 5000  # ~130KB
        article = Article(
            url="https://example.com/long-full-text",
            title="Long Content Article",
            section="news",
            full_text=long_text,
            news_source_id=1,
        )
        repository = ArticleRepository()

        # When: the article is inserted
        result = await repository.insert_article(db_connection, article)

        # Then: successfully inserts (TEXT type handles large content)
        assert result.id is not None
        assert result.full_text == long_text

    async def test_fetched_at_defaults_to_current_time(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article without explicit fetched_at
        before_insert = datetime.now(timezone.utc)
        article = Article(
            url="https://example.com/default-fetched-at",
            title="Default Fetched At Article",
            section="news",
            news_source_id=1,
        )
        repository = ArticleRepository()

        # When: the article is inserted
        result = await repository.insert_article(db_connection, article)
        after_insert = datetime.now(timezone.utc)

        # Then: returns article with fetched_at close to current time
        assert result.id is not None
        assert result.fetched_at is not None
        # Allow 1 second tolerance for test execution time
        assert before_insert - timedelta(seconds=1) <= result.fetched_at <= after_insert + timedelta(seconds=1)

    async def test_with_custom_fetched_at(
        self,
        db_connection: asyncpg.Connection,
    ):
        # Given: an article with explicit fetched_at value
        custom_fetched_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        article = Article(
            url="https://example.com/custom-fetched-at",
            title="Custom Fetched At Article",
            section="news",
            fetched_at=custom_fetched_at,
            news_source_id=1,
        )
        repository = ArticleRepository()

        # When: the article is inserted
        result = await repository.insert_article(db_connection, article)

        # Then: returns article with the custom fetched_at preserved
        assert result.id is not None
        assert result.fetched_at == custom_fetched_at
