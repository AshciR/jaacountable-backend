import pytest
from datetime import datetime, timezone, timedelta
import asyncpg

from src.article_persistence.models.domain import Entity
from src.article_persistence.repositories.entity_repository import EntityRepository
from tests.article_persistence.utils import (
    create_test_article,
    create_test_article_entity,
    create_test_entity,
    create_test_news_source,
)


class TestFindByNormalizedNameHappyPath:
    """Happy path tests for find_by_normalized_name."""

    async def test_find_existing_entity_succeeds(self, db_connection: asyncpg.Connection):
        """Test finding entity by normalized name returns entity."""
        # Given: an entity exists in database
        created_entity = await create_test_entity(
            db_connection,
            name="Ruel Reid",
            normalized_name="ruel reid",
        )

        # When: searching by normalized name
        repository = EntityRepository()
        result = await repository.find_by_normalized_name(
            db_connection,
            normalized_name="ruel reid",
        )

        # Then: entity is returned with all fields populated
        assert result is not None
        assert result.id == created_entity.id
        assert result.name == "Ruel Reid"
        assert result.normalized_name == "ruel reid"
        assert result.created_at is not None

    async def test_find_nonexistent_entity_returns_none(self, db_connection: asyncpg.Connection):
        """Test finding nonexistent entity returns None."""
        # Given: no entity with normalized name exists
        repository = EntityRepository()

        # When: searching by normalized name
        result = await repository.find_by_normalized_name(
            db_connection,
            normalized_name="nonexistent entity",
        )

        # Then: None is returned
        assert result is None


class TestInsertEntityHappyPath:
    """Happy path tests for insert_entity."""

    async def test_insert_with_all_fields_succeeds(self, db_connection: asyncpg.Connection):
        """Test inserting entity with all fields populated."""
        # Given: a valid Entity with name and normalized_name
        entity = Entity(
            name="Fritz Pinnock",
            normalized_name="fritz pinnock",
        )
        repository = EntityRepository()

        # When: entity is inserted
        result = await repository.insert_entity(db_connection, entity)

        # Then: returned entity has database-generated id and matching fields
        assert result.id is not None
        assert result.name == "Fritz Pinnock"
        assert result.normalized_name == "fritz pinnock"
        assert result.created_at is not None

    async def test_insert_with_default_created_at_succeeds(self, db_connection: asyncpg.Connection):
        """Test inserting entity uses default created_at."""
        # Given: an Entity without explicit created_at
        before_insert = datetime.now(timezone.utc)
        entity = Entity(
            name="OCG",
            normalized_name="ocg",
        )
        repository = EntityRepository()

        # When: entity is inserted
        result = await repository.insert_entity(db_connection, entity)
        after_insert = datetime.now(timezone.utc)

        # Then: created_at defaults to current UTC time
        assert result.created_at is not None
        assert before_insert - timedelta(seconds=1) <= result.created_at <= after_insert + timedelta(seconds=1)

    async def test_whitespace_stripped_from_fields(self, db_connection: asyncpg.Connection):
        """Test whitespace is stripped from name and normalized_name."""
        # Given: an Entity with whitespace in name fields
        entity = Entity(
            name="  Ministry of Education  ",
            normalized_name="  ministry of education  ",
        )
        repository = EntityRepository()

        # When: entity is inserted
        result = await repository.insert_entity(db_connection, entity)

        # Then: whitespace is stripped by Pydantic validators
        assert result.name == "Ministry of Education"
        assert result.normalized_name == "ministry of education"


class TestInsertEntityDatabaseConstraints:
    """Database constraint tests for insert_entity."""

    async def test_duplicate_normalized_name_raises_unique_violation(self, db_connection: asyncpg.Connection):
        """Test duplicate normalized_name raises UniqueViolationError."""
        # Given: an entity with normalized_name "test entity" exists
        await create_test_entity(
            db_connection,
            name="Test Entity",
            normalized_name="test entity",
        )

        # When: inserting another entity with same normalized_name
        repository = EntityRepository()
        duplicate_entity = Entity(
            name="Test Entity Different Name",
            normalized_name="test entity",
        )

        # Then: UniqueViolationError is raised
        with pytest.raises(asyncpg.UniqueViolationError):
            await repository.insert_entity(db_connection, duplicate_entity)


class TestInsertEntityEdgeCases:
    """Edge case tests for insert_entity."""

    async def test_unicode_in_name_succeeds(self, db_connection: asyncpg.Connection):
        """Test entity names with Unicode characters."""
        # Given: an Entity with Unicode characters in name
        entity = Entity(
            name="José González",
            normalized_name="jose gonzalez",
        )
        repository = EntityRepository()

        # When: entity is inserted
        result = await repository.insert_entity(db_connection, entity)

        # Then: Unicode is preserved correctly
        assert result.name == "José González"
        assert result.normalized_name == "jose gonzalez"

    async def test_very_long_name_succeeds(self, db_connection: asyncpg.Connection):
        """Test very long entity names."""
        # Given: an Entity with very long name (500+ chars)
        long_name = "A" * 500
        long_normalized = "a" * 500
        entity = Entity(
            name=long_name,
            normalized_name=long_normalized,
        )
        repository = EntityRepository()

        # When: entity is inserted
        result = await repository.insert_entity(db_connection, entity)

        # Then: insert succeeds
        assert result.name == long_name
        assert result.normalized_name == long_normalized


class TestFindEntitiesByArticleIdHappyPath:
    """Happy path tests for find_entities_by_article_id."""

    async def test_find_multiple_entities_for_article(self, db_connection: asyncpg.Connection):
        """Test finding multiple entities linked to article."""
        # Given: an article linked to 3 entities
        news_source = await create_test_news_source(db_connection)
        article = await create_test_article(
            db_connection,
            url="https://example.com/article1",
            news_source_id=news_source.id,
        )
        entity1 = await create_test_entity(db_connection, name="Entity 1", normalized_name="entity 1")
        entity2 = await create_test_entity(db_connection, name="Entity 2", normalized_name="entity 2")
        entity3 = await create_test_entity(db_connection, name="Entity 3", normalized_name="entity 3")

        await create_test_article_entity(db_connection, article.id, entity1.id)
        await create_test_article_entity(db_connection, article.id, entity2.id)
        await create_test_article_entity(db_connection, article.id, entity3.id)

        # When: finding entities by article_id
        repository = EntityRepository()
        results = await repository.find_entities_by_article_id(db_connection, article.id)

        # Then: all 3 entities are returned
        assert len(results) == 3
        entity_names = [e.name for e in results]
        assert "Entity 1" in entity_names
        assert "Entity 2" in entity_names
        assert "Entity 3" in entity_names

    async def test_find_entities_returns_empty_list_when_none(self, db_connection: asyncpg.Connection):
        """Test finding entities for article with no entities returns empty list."""
        # Given: an article with no entity associations
        news_source = await create_test_news_source(db_connection)
        article = await create_test_article(
            db_connection,
            url="https://example.com/article2",
            news_source_id=news_source.id,
        )

        # When: finding entities by article_id
        repository = EntityRepository()
        results = await repository.find_entities_by_article_id(db_connection, article.id)

        # Then: empty list is returned
        assert results == []

    async def test_find_entities_ordered_by_name(self, db_connection: asyncpg.Connection):
        """Test entities are returned ordered by name alphabetically."""
        # Given: an article linked to 3 entities with different names
        news_source = await create_test_news_source(db_connection)
        article = await create_test_article(
            db_connection,
            url="https://example.com/article3",
            news_source_id=news_source.id,
        )
        entity_z = await create_test_entity(db_connection, name="Zebra", normalized_name="zebra")
        entity_a = await create_test_entity(db_connection, name="Apple", normalized_name="apple")
        entity_m = await create_test_entity(db_connection, name="Mango", normalized_name="mango")

        # Create associations in non-alphabetical order
        await create_test_article_entity(db_connection, article.id, entity_z.id)
        await create_test_article_entity(db_connection, article.id, entity_a.id)
        await create_test_article_entity(db_connection, article.id, entity_m.id)

        # When: finding entities by article_id
        repository = EntityRepository()
        results = await repository.find_entities_by_article_id(db_connection, article.id)

        # Then: entities are ordered alphabetically by name
        assert len(results) == 3
        assert results[0].name == "Apple"
        assert results[1].name == "Mango"
        assert results[2].name == "Zebra"


class TestFindArticleIdsByEntityIdHappyPath:
    """Happy path tests for find_article_ids_by_entity_id."""

    async def test_find_multiple_articles_for_entity(self, db_connection: asyncpg.Connection):
        """Test finding multiple articles linked to entity."""
        # Given: an entity linked to 3 articles
        news_source = await create_test_news_source(db_connection)
        article1 = await create_test_article(db_connection, url="https://example.com/a1", news_source_id=news_source.id)
        article2 = await create_test_article(db_connection, url="https://example.com/a2", news_source_id=news_source.id)
        article3 = await create_test_article(db_connection, url="https://example.com/a3", news_source_id=news_source.id)

        entity = await create_test_entity(db_connection, name="Common Entity", normalized_name="common entity")

        await create_test_article_entity(db_connection, article1.id, entity.id)
        await create_test_article_entity(db_connection, article2.id, entity.id)
        await create_test_article_entity(db_connection, article3.id, entity.id)

        # When: finding article IDs by entity_id
        repository = EntityRepository()
        results = await repository.find_article_ids_by_entity_id(db_connection, entity.id)

        # Then: all 3 article IDs are returned
        assert len(results) == 3
        assert article1.id in results
        assert article2.id in results
        assert article3.id in results

    async def test_find_articles_returns_empty_list_when_none(self, db_connection: asyncpg.Connection):
        """Test finding articles for entity with no associations returns empty list."""
        # Given: an entity with no article associations
        entity = await create_test_entity(db_connection, name="Lonely Entity", normalized_name="lonely entity")

        # When: finding article IDs by entity_id
        repository = EntityRepository()
        results = await repository.find_article_ids_by_entity_id(db_connection, entity.id)

        # Then: empty list is returned
        assert results == []

    async def test_find_articles_ordered_by_article_id(self, db_connection: asyncpg.Connection):
        """Test article IDs are returned ordered by article_id."""
        # Given: an entity linked to 3 articles
        news_source = await create_test_news_source(db_connection)
        article1 = await create_test_article(db_connection, url="https://example.com/b1", news_source_id=news_source.id)
        article2 = await create_test_article(db_connection, url="https://example.com/b2", news_source_id=news_source.id)
        article3 = await create_test_article(db_connection, url="https://example.com/b3", news_source_id=news_source.id)

        entity = await create_test_entity(db_connection, name="Test Entity", normalized_name="test entity ordered")

        # Create associations in reverse order
        await create_test_article_entity(db_connection, article3.id, entity.id)
        await create_test_article_entity(db_connection, article1.id, entity.id)
        await create_test_article_entity(db_connection, article2.id, entity.id)

        # When: finding article IDs by entity_id
        repository = EntityRepository()
        results = await repository.find_article_ids_by_entity_id(db_connection, entity.id)

        # Then: article IDs are ordered numerically
        assert len(results) == 3
        assert results == sorted(results)
        assert results[0] == article1.id
        assert results[1] == article2.id
        assert results[2] == article3.id
