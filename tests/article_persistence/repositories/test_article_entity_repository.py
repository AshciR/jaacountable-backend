import pytest
from datetime import datetime, timezone
import asyncpg

from src.article_persistence.models.domain import ArticleEntity
from src.article_persistence.repositories.article_entity_repository import ArticleEntityRepository
from tests.article_persistence.repositories.utils import (
    check_record_exists,
    create_test_article,
    create_test_entity,
    create_test_news_source,
    delete_article,
    delete_entity,
)


class TestLinkArticleToEntityHappyPath:
    """Happy path tests for link_article_to_entity."""

    async def test_link_with_valid_ids_succeeds(self, db_connection: asyncpg.Connection):
        """Test linking article to entity with valid IDs."""
        # Given: a valid article and entity exist
        news_source = await create_test_news_source(db_connection)
        article = await create_test_article(
            db_connection,
            url="https://example.com/article1",
            news_source_id=news_source.id,
        )
        entity = await create_test_entity(
            db_connection,
            name="Ruel Reid",
            normalized_name="ruel reid",
        )

        # When: linking them together with classifier_type
        repository = ArticleEntityRepository()
        article_entity = ArticleEntity(
            article_id=article.id,
            entity_id=entity.id,
            classifier_type="CORRUPTION",
        )
        result = await repository.link_article_to_entity(db_connection, article_entity)

        # Then: association is created with database-generated id
        assert result.id is not None
        assert result.article_id == article.id
        assert result.entity_id == entity.id
        assert result.classifier_type == "CORRUPTION"
        assert result.created_at is not None

    async def test_link_multiple_entities_to_same_article(self, db_connection: asyncpg.Connection):
        """Test linking multiple entities to same article."""
        # Given: one article and three entities
        news_source = await create_test_news_source(db_connection)
        article = await create_test_article(
            db_connection,
            url="https://example.com/article2",
            news_source_id=news_source.id,
        )
        entity1 = await create_test_entity(db_connection, name="Entity 1", normalized_name="entity 1")
        entity2 = await create_test_entity(db_connection, name="Entity 2", normalized_name="entity 2")
        entity3 = await create_test_entity(db_connection, name="Entity 3", normalized_name="entity 3")

        # When: linking all entities to the article
        repository = ArticleEntityRepository()
        result1 = await repository.link_article_to_entity(
            db_connection,
            ArticleEntity(article_id=article.id, entity_id=entity1.id, classifier_type="CORRUPTION"),
        )
        result2 = await repository.link_article_to_entity(
            db_connection,
            ArticleEntity(article_id=article.id, entity_id=entity2.id, classifier_type="CORRUPTION"),
        )
        result3 = await repository.link_article_to_entity(
            db_connection,
            ArticleEntity(article_id=article.id, entity_id=entity3.id, classifier_type="CORRUPTION"),
        )

        # Then: all associations are created successfully
        assert result1.id is not None
        assert result2.id is not None
        assert result3.id is not None
        assert len(set([result1.id, result2.id, result3.id])) == 3


class TestLinkArticleToEntityDatabaseConstraints:
    """Database constraint tests for link_article_to_entity."""

    async def test_duplicate_article_entity_pair_raises_unique_violation(self, db_connection: asyncpg.Connection):
        """Test duplicate (article_id, entity_id) raises UniqueViolationError."""
        # Given: article-entity association already exists
        news_source = await create_test_news_source(db_connection)
        article = await create_test_article(
            db_connection,
            url="https://example.com/article3",
            news_source_id=news_source.id,
        )
        entity = await create_test_entity(db_connection, name="Duplicate Test", normalized_name="duplicate test")

        repository = ArticleEntityRepository()
        article_entity = ArticleEntity(
            article_id=article.id,
            entity_id=entity.id,
            classifier_type="CORRUPTION",
        )
        await repository.link_article_to_entity(db_connection, article_entity)

        # When: attempting to create same association again
        duplicate_article_entity = ArticleEntity(
            article_id=article.id,
            entity_id=entity.id,
            classifier_type="CORRUPTION",
        )

        # Then: UniqueViolationError is raised
        with pytest.raises(asyncpg.UniqueViolationError):
            await repository.link_article_to_entity(db_connection, duplicate_article_entity)

    async def test_invalid_article_id_raises_foreign_key_violation(self, db_connection: asyncpg.Connection):
        """Test invalid article_id raises ForeignKeyViolationError."""
        # Given: article_id that doesn't exist
        entity = await create_test_entity(db_connection, name="FK Test 1", normalized_name="fk test 1")
        invalid_article_id = 999999

        # When: attempting to link to entity
        repository = ArticleEntityRepository()
        article_entity = ArticleEntity(
            article_id=invalid_article_id,
            entity_id=entity.id,
            classifier_type="CORRUPTION",
        )

        # Then: ForeignKeyViolationError is raised
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await repository.link_article_to_entity(db_connection, article_entity)

    async def test_invalid_entity_id_raises_foreign_key_violation(self, db_connection: asyncpg.Connection):
        """Test invalid entity_id raises ForeignKeyViolationError."""
        # Given: entity_id that doesn't exist
        news_source = await create_test_news_source(db_connection)
        article = await create_test_article(
            db_connection,
            url="https://example.com/article4",
            news_source_id=news_source.id,
        )
        invalid_entity_id = 999999

        # When: attempting to link to article
        repository = ArticleEntityRepository()
        article_entity = ArticleEntity(
            article_id=article.id,
            entity_id=invalid_entity_id,
            classifier_type="CORRUPTION",
        )

        # Then: ForeignKeyViolationError is raised
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await repository.link_article_to_entity(db_connection, article_entity)

    async def test_cascade_delete_when_article_deleted(self, db_connection: asyncpg.Connection):
        """Test article-entity association is deleted when article is deleted."""
        # Given: article-entity association exists
        news_source = await create_test_news_source(db_connection)
        article = await create_test_article(
            db_connection,
            url="https://example.com/article5",
            news_source_id=news_source.id,
        )
        entity = await create_test_entity(db_connection, name="Cascade Test 1", normalized_name="cascade test 1")

        repository = ArticleEntityRepository()
        article_entity = ArticleEntity(
            article_id=article.id,
            entity_id=entity.id,
            classifier_type="CORRUPTION",
        )
        result = await repository.link_article_to_entity(db_connection, article_entity)
        association_id = result.id

        # When: article is deleted
        await delete_article(db_connection, article.id)

        # Then: association is automatically deleted (CASCADE)
        assert not await check_record_exists(db_connection, "article_entities", association_id)

    async def test_cascade_delete_when_entity_deleted(self, db_connection: asyncpg.Connection):
        """Test article-entity association is deleted when entity is deleted."""
        # Given: article-entity association exists
        news_source = await create_test_news_source(db_connection)
        article = await create_test_article(
            db_connection,
            url="https://example.com/article6",
            news_source_id=news_source.id,
        )
        entity = await create_test_entity(db_connection, name="Cascade Test 2", normalized_name="cascade test 2")

        repository = ArticleEntityRepository()
        article_entity = ArticleEntity(
            article_id=article.id,
            entity_id=entity.id,
            classifier_type="CORRUPTION",
        )
        result = await repository.link_article_to_entity(db_connection, article_entity)
        association_id = result.id

        # When: entity is deleted
        await delete_entity(db_connection, entity.id)

        # Then: association is automatically deleted (CASCADE)
        assert not await check_record_exists(db_connection, "article_entities", association_id)
