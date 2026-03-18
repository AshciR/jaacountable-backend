import pytest
from datetime import date, datetime, timezone, timedelta
import asyncpg

from src.article_persistence.models.domain import Article, Entity
from src.article_persistence.repositories.article_repository import ArticleRepository
from src.article_persistence.repositories.entity_repository import EntityRepository
from tests.article_persistence.utils import (
    create_test_article,
    create_test_article_entity,
    create_test_entity,
    create_test_news_source,
)


async def _insert_article_with_date(
    conn: asyncpg.Connection,
    url: str,
    published_date: datetime = datetime(2024, 1, 1, tzinfo=timezone.utc),
    news_source_id: int = 1,
) -> Article:
    """Insert a minimal article with a specific published_date."""
    repo = ArticleRepository()
    article = Article(
        url=url,
        title="Test article",
        section="news",
        full_text="Some content.",
        published_date=published_date,
        news_source_id=news_source_id,
    )
    return await repo.insert_article(conn, article)


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


# ---------------------------------------------------------------------------
# list_entities
# ---------------------------------------------------------------------------


class TestListEntitiesHappyPath:
    """Happy path tests for list_entities."""

    async def test_returns_entity_with_article_count(self, db_connection: asyncpg.Connection):
        # Given: an entity linked to 2 articles
        entity = await create_test_entity(db_connection, name="Petrojam", normalized_name="petrojam lp")
        article1 = await _insert_article_with_date(db_connection, url="https://example.com/le-1")
        article2 = await _insert_article_with_date(db_connection, url="https://example.com/le-2")
        await create_test_article_entity(db_connection, article1.id, entity.id)
        await create_test_article_entity(db_connection, article2.id, entity.id)

        # When: listing entities
        repo = EntityRepository()
        results, total = await repo.list_entities(db_connection)

        # Then: entity appears with article_count=2
        match = next((r for r in results if r.normalized_name == "petrojam lp"), None)
        assert match is not None
        assert match.name == "Petrojam"
        assert match.article_count == 2

    async def test_returns_correct_last_seen_date(self, db_connection: asyncpg.Connection):
        # Given: an entity linked to articles with different published dates
        entity = await create_test_entity(db_connection, name="NWA", normalized_name="nwa lp")
        old = await _insert_article_with_date(
            db_connection,
            url="https://example.com/le-old",
            published_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )
        new = await _insert_article_with_date(
            db_connection,
            url="https://example.com/le-new",
            published_date=datetime(2024, 6, 15, tzinfo=timezone.utc),
        )
        await create_test_article_entity(db_connection, old.id, entity.id)
        await create_test_article_entity(db_connection, new.id, entity.id)

        # When: listing entities
        repo = EntityRepository()
        results, _ = await repo.list_entities(db_connection)

        # Then: last_seen_date is the most recent article date
        match = next((r for r in results if r.normalized_name == "nwa lp"), None)
        assert match is not None
        assert match.last_seen_date.date() == date(2024, 6, 15)

    async def test_entity_with_no_articles_is_excluded(self, db_connection: asyncpg.Connection):
        # Given: an entity with no article links
        await create_test_entity(db_connection, name="Orphan Entity", normalized_name="orphan entity lp")

        # When: listing entities
        repo = EntityRepository()
        results, _ = await repo.list_entities(db_connection)

        # Then: the orphan entity is not in results (INNER JOIN excludes it)
        names = [r.normalized_name for r in results]
        assert "orphan entity lp" not in names

    async def test_total_reflects_distinct_entity_count(self, db_connection: asyncpg.Connection):
        # Given: 3 entities each linked to 1 article
        for i in range(3):
            entity = await create_test_entity(
                db_connection,
                name=f"Total Entity {i}",
                normalized_name=f"total entity lp {i}",
            )
            article = await _insert_article_with_date(
                db_connection, url=f"https://example.com/le-total-{i}"
            )
            await create_test_article_entity(db_connection, article.id, entity.id)

        # When: listing with page_size=1
        repo = EntityRepository()
        results, total = await repo.list_entities(db_connection, page=1, page_size=1)

        # Then: only 1 result returned but total >= 3
        assert len(results) == 1
        assert total >= 3


class TestListEntitiesSorting:
    """Sorting behaviour for list_entities."""

    async def test_sort_latest_orders_by_most_recent_date(self, db_connection: asyncpg.Connection):
        # Given: two entities with different last-seen dates
        entity_old = await create_test_entity(
            db_connection, name="Old Entity", normalized_name="old entity sort"
        )
        entity_new = await create_test_entity(
            db_connection, name="New Entity", normalized_name="new entity sort"
        )
        old_article = await _insert_article_with_date(
            db_connection,
            url="https://example.com/sort-old",
            published_date=datetime(2022, 1, 1, tzinfo=timezone.utc),
        )
        new_article = await _insert_article_with_date(
            db_connection,
            url="https://example.com/sort-new",
            published_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        await create_test_article_entity(db_connection, old_article.id, entity_old.id)
        await create_test_article_entity(db_connection, new_article.id, entity_new.id)

        # When: listing with sort=latest
        repo = EntityRepository()
        results, _ = await repo.list_entities(db_connection, sort="latest")

        # Then: entity with newer article appears first
        names = [r.normalized_name for r in results]
        assert names.index("new entity sort") < names.index("old entity sort")

    async def test_sort_most_found_orders_by_article_count(self, db_connection: asyncpg.Connection):
        # Given: two entities — one linked to 3 articles, one to 1
        entity_rare = await create_test_entity(
            db_connection, name="Rare Entity", normalized_name="rare entity sort"
        )
        entity_common = await create_test_entity(
            db_connection, name="Common Entity", normalized_name="common entity sort"
        )
        rare_article = await _insert_article_with_date(
            db_connection, url="https://example.com/mf-rare"
        )
        await create_test_article_entity(db_connection, rare_article.id, entity_rare.id)

        for i in range(3):
            article = await _insert_article_with_date(
                db_connection, url=f"https://example.com/mf-common-{i}"
            )
            await create_test_article_entity(db_connection, article.id, entity_common.id)

        # When: listing with sort=most_found
        repo = EntityRepository()
        results, _ = await repo.list_entities(db_connection, sort="most_found")

        # Then: entity with more articles appears first
        names = [r.normalized_name for r in results]
        assert names.index("common entity sort") < names.index("rare entity sort")


class TestListEntitiesSinceFilter:
    """since parameter scopes article_count and last_seen_date."""

    async def test_since_excludes_articles_before_date(self, db_connection: asyncpg.Connection):
        # Given: an entity linked to one old article and one recent article
        entity = await create_test_entity(
            db_connection, name="Scoped Entity", normalized_name="scoped entity since"
        )
        old_article = await _insert_article_with_date(
            db_connection,
            url="https://example.com/since-old",
            published_date=datetime(2020, 6, 1, tzinfo=timezone.utc),
        )
        new_article = await _insert_article_with_date(
            db_connection,
            url="https://example.com/since-new",
            published_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        await create_test_article_entity(db_connection, old_article.id, entity.id)
        await create_test_article_entity(db_connection, new_article.id, entity.id)

        # When: listing with since=2023-01-01
        repo = EntityRepository()
        results, _ = await repo.list_entities(
            db_connection, since=date(2023, 1, 1)
        )

        # Then: article_count reflects only the recent article
        match = next((r for r in results if r.normalized_name == "scoped entity since"), None)
        assert match is not None
        assert match.article_count == 1

    async def test_since_scopes_last_seen_date(self, db_connection: asyncpg.Connection):
        # Given: an entity with articles spanning 2020–2024
        entity = await create_test_entity(
            db_connection, name="Date Scoped", normalized_name="date scoped since"
        )
        for year, url_suffix in [(2020, "ds-2020"), (2022, "ds-2022"), (2024, "ds-2024")]:
            article = await _insert_article_with_date(
                db_connection,
                url=f"https://example.com/{url_suffix}",
                published_date=datetime(year, 1, 1, tzinfo=timezone.utc),
            )
            await create_test_article_entity(db_connection, article.id, entity.id)

        # When: listing with since=2021-01-01
        repo = EntityRepository()
        results, _ = await repo.list_entities(
            db_connection, since=date(2021, 1, 1)
        )

        # Then: last_seen_date is 2024, not 2020 (2020 article excluded)
        match = next((r for r in results if r.normalized_name == "date scoped since"), None)
        assert match is not None
        assert match.last_seen_date.year == 2024
        assert match.article_count == 2

    async def test_since_entity_with_all_old_articles_excluded(self, db_connection: asyncpg.Connection):
        # Given: an entity whose only article predates the since cutoff
        entity = await create_test_entity(
            db_connection, name="Ancient Entity", normalized_name="ancient entity since"
        )
        old_article = await _insert_article_with_date(
            db_connection,
            url="https://example.com/ancient",
            published_date=datetime(2019, 1, 1, tzinfo=timezone.utc),
        )
        await create_test_article_entity(db_connection, old_article.id, entity.id)

        # When: listing with since=2023-01-01
        repo = EntityRepository()
        results, _ = await repo.list_entities(
            db_connection, since=date(2023, 1, 1)
        )

        # Then: the entity does not appear (no articles in window)
        names = [r.normalized_name for r in results]
        assert "ancient entity since" not in names

    async def test_since_boundary_is_inclusive(self, db_connection: asyncpg.Connection):
        # Given: an entity with an article published exactly on the since date
        entity = await create_test_entity(
            db_connection, name="Boundary Entity", normalized_name="boundary entity since"
        )
        boundary_date = date(2024, 3, 15)
        article = await _insert_article_with_date(
            db_connection,
            url="https://example.com/boundary-since",
            published_date=datetime(2024, 3, 15, tzinfo=timezone.utc),
        )
        await create_test_article_entity(db_connection, article.id, entity.id)

        # When: listing with since equal to the article's published date
        repo = EntityRepository()
        results, _ = await repo.list_entities(db_connection, since=boundary_date)

        # Then: the entity is included (>= is inclusive)
        names = [r.normalized_name for r in results]
        assert "boundary entity since" in names


class TestListEntitiesPagination:
    """Pagination behaviour for list_entities."""

    async def test_page_size_limits_results(self, db_connection: asyncpg.Connection):
        # Given: 5 entities each linked to an article
        for i in range(5):
            entity = await create_test_entity(
                db_connection,
                name=f"Paginate Entity {i}",
                normalized_name=f"paginate entity pg {i}",
            )
            article = await _insert_article_with_date(
                db_connection, url=f"https://example.com/pg-{i}"
            )
            await create_test_article_entity(db_connection, article.id, entity.id)

        # When: listing with page_size=3
        repo = EntityRepository()
        results, _ = await repo.list_entities(db_connection, page=1, page_size=3)

        # Then: exactly 3 results are returned
        assert len(results) == 3

    async def test_page_2_returns_different_items(self, db_connection: asyncpg.Connection):
        # Given: 4 entities each linked to an article
        for i in range(4):
            entity = await create_test_entity(
                db_connection,
                name=f"Offset Entity {i}",
                normalized_name=f"offset entity pg {i}",
            )
            article = await _insert_article_with_date(
                db_connection, url=f"https://example.com/off-{i}"
            )
            await create_test_article_entity(db_connection, article.id, entity.id)

        # When: fetching page 1 and page 2 with page_size=2
        repo = EntityRepository()
        page1, _ = await repo.list_entities(db_connection, page=1, page_size=2)
        page2, _ = await repo.list_entities(db_connection, page=2, page_size=2)

        # Then: pages are non-overlapping
        page1_names = {r.normalized_name for r in page1}
        page2_names = {r.normalized_name for r in page2}
        assert page1_names.isdisjoint(page2_names)

    async def test_total_count_independent_of_page(self, db_connection: asyncpg.Connection):
        # Given: 6 entities each linked to an article
        for i in range(6):
            entity = await create_test_entity(
                db_connection,
                name=f"Total Count Entity {i}",
                normalized_name=f"total count entity pg {i}",
            )
            article = await _insert_article_with_date(
                db_connection, url=f"https://example.com/tc-{i}"
            )
            await create_test_article_entity(db_connection, article.id, entity.id)

        # When: fetching page 1 with page_size=2
        repo = EntityRepository()
        results, total = await repo.list_entities(db_connection, page=1, page_size=2)

        # Then: 2 results returned but total >= 6
        assert len(results) == 2
        assert total >= 6
