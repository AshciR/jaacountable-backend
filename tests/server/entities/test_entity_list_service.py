"""Tests for EntityListService.list_entities()."""

import asyncpg
from datetime import date, datetime, timezone

from src.server.entities.schemas import EntityListParams
from src.server.entities.service import EntityListService
from tests.article_persistence.utils import (
    create_test_article_entity,
    create_test_entity,
    insert_article_with_date,
)


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


class TestListEntitiesHappyPath:
    """Happy path tests for list_entities."""

    async def test_returns_entity_with_article_count(self, db_connection: asyncpg.Connection):
        # Given: an entity linked to 2 articles
        entity = await create_test_entity(db_connection, name="Petrojam", normalized_name="petrojam lp")
        article1 = await insert_article_with_date(db_connection, url="https://example.com/le-1")
        article2 = await insert_article_with_date(db_connection, url="https://example.com/le-2")
        await create_test_article_entity(db_connection, article1.id, entity.id)
        await create_test_article_entity(db_connection, article2.id, entity.id)

        # When: listing entities
        service = EntityListService()
        results, total = await service.list_entities(db_connection, EntityListParams())

        # Then: entity appears with article_count=2
        match = next((r for r in results if r.normalized_name == "petrojam lp"), None)
        assert match is not None
        assert match.name == "Petrojam"
        assert match.article_count == 2

    async def test_returns_correct_last_seen_date(self, db_connection: asyncpg.Connection):
        # Given: an entity linked to articles with different published dates
        entity = await create_test_entity(db_connection, name="NWA", normalized_name="nwa lp")
        old = await insert_article_with_date(
            db_connection,
            url="https://example.com/le-old",
            published_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )
        new = await insert_article_with_date(
            db_connection,
            url="https://example.com/le-new",
            published_date=datetime(2024, 6, 15, tzinfo=timezone.utc),
        )
        await create_test_article_entity(db_connection, old.id, entity.id)
        await create_test_article_entity(db_connection, new.id, entity.id)

        # When: listing entities
        service = EntityListService()
        results, _ = await service.list_entities(db_connection, EntityListParams())

        # Then: last_seen_date is the most recent article date
        match = next((r for r in results if r.normalized_name == "nwa lp"), None)
        assert match is not None
        assert match.last_seen_date.date() == date(2024, 6, 15)

    async def test_entity_with_no_articles_is_excluded(self, db_connection: asyncpg.Connection):
        # Given: an entity with no article links
        await create_test_entity(db_connection, name="Orphan Entity", normalized_name="orphan entity lp")

        # When: listing entities
        service = EntityListService()
        results, _ = await service.list_entities(db_connection, EntityListParams())

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
            article = await insert_article_with_date(
                db_connection, url=f"https://example.com/le-total-{i}"
            )
            await create_test_article_entity(db_connection, article.id, entity.id)

        # When: listing with page_size=1
        service = EntityListService()
        results, total = await service.list_entities(
            db_connection, EntityListParams(page=1, page_size=1)
        )

        # Then: only 1 result returned but total >= 3
        assert len(results) == 1
        assert total >= 3


# ---------------------------------------------------------------------------
# Sorting tests
# ---------------------------------------------------------------------------


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
        old_article = await insert_article_with_date(
            db_connection,
            url="https://example.com/sort-old",
            published_date=datetime(2022, 1, 1, tzinfo=timezone.utc),
        )
        new_article = await insert_article_with_date(
            db_connection,
            url="https://example.com/sort-new",
            published_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        await create_test_article_entity(db_connection, old_article.id, entity_old.id)
        await create_test_article_entity(db_connection, new_article.id, entity_new.id)

        # When: listing with sort=latest
        service = EntityListService()
        results, _ = await service.list_entities(
            db_connection, EntityListParams(sort="latest")
        )

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
        rare_article = await insert_article_with_date(
            db_connection, url="https://example.com/mf-rare"
        )
        await create_test_article_entity(db_connection, rare_article.id, entity_rare.id)

        for i in range(3):
            article = await insert_article_with_date(
                db_connection, url=f"https://example.com/mf-common-{i}"
            )
            await create_test_article_entity(db_connection, article.id, entity_common.id)

        # When: listing with sort=most_found
        service = EntityListService()
        results, _ = await service.list_entities(
            db_connection, EntityListParams(sort="most_found")
        )

        # Then: entity with more articles appears first
        names = [r.normalized_name for r in results]
        assert names.index("common entity sort") < names.index("rare entity sort")


# ---------------------------------------------------------------------------
# Since filter tests
# ---------------------------------------------------------------------------


class TestListEntitiesSinceFilter:
    """since parameter scopes article_count and last_seen_date."""

    async def test_since_excludes_articles_before_date(self, db_connection: asyncpg.Connection):
        # Given: an entity linked to one old article and one recent article
        entity = await create_test_entity(
            db_connection, name="Scoped Entity", normalized_name="scoped entity since"
        )
        old_article = await insert_article_with_date(
            db_connection,
            url="https://example.com/since-old",
            published_date=datetime(2020, 6, 1, tzinfo=timezone.utc),
        )
        new_article = await insert_article_with_date(
            db_connection,
            url="https://example.com/since-new",
            published_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        await create_test_article_entity(db_connection, old_article.id, entity.id)
        await create_test_article_entity(db_connection, new_article.id, entity.id)

        # When: listing with since=2023-01-01
        service = EntityListService()
        results, _ = await service.list_entities(
            db_connection, EntityListParams(since=date(2023, 1, 1))
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
            article = await insert_article_with_date(
                db_connection,
                url=f"https://example.com/{url_suffix}",
                published_date=datetime(year, 1, 1, tzinfo=timezone.utc),
            )
            await create_test_article_entity(db_connection, article.id, entity.id)

        # When: listing with since=2021-01-01
        service = EntityListService()
        results, _ = await service.list_entities(
            db_connection, EntityListParams(since=date(2021, 1, 1))
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
        old_article = await insert_article_with_date(
            db_connection,
            url="https://example.com/ancient",
            published_date=datetime(2019, 1, 1, tzinfo=timezone.utc),
        )
        await create_test_article_entity(db_connection, old_article.id, entity.id)

        # When: listing with since=2023-01-01
        service = EntityListService()
        results, _ = await service.list_entities(
            db_connection, EntityListParams(since=date(2023, 1, 1))
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
        article = await insert_article_with_date(
            db_connection,
            url="https://example.com/boundary-since",
            published_date=datetime(2024, 3, 15, tzinfo=timezone.utc),
        )
        await create_test_article_entity(db_connection, article.id, entity.id)

        # When: listing with since equal to the article's published date
        service = EntityListService()
        results, _ = await service.list_entities(
            db_connection, EntityListParams(since=boundary_date)
        )

        # Then: the entity is included (>= is inclusive)
        names = [r.normalized_name for r in results]
        assert "boundary entity since" in names


# ---------------------------------------------------------------------------
# Pagination tests
# ---------------------------------------------------------------------------


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
            article = await insert_article_with_date(
                db_connection, url=f"https://example.com/pg-{i}"
            )
            await create_test_article_entity(db_connection, article.id, entity.id)

        # When: listing with page_size=3
        service = EntityListService()
        results, _ = await service.list_entities(
            db_connection, EntityListParams(page=1, page_size=3)
        )

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
            article = await insert_article_with_date(
                db_connection, url=f"https://example.com/off-{i}"
            )
            await create_test_article_entity(db_connection, article.id, entity.id)

        # When: fetching page 1 and page 2 with page_size=2
        service = EntityListService()
        page1, _ = await service.list_entities(
            db_connection, EntityListParams(page=1, page_size=2)
        )
        page2, _ = await service.list_entities(
            db_connection, EntityListParams(page=2, page_size=2)
        )

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
            article = await insert_article_with_date(
                db_connection, url=f"https://example.com/tc-{i}"
            )
            await create_test_article_entity(db_connection, article.id, entity.id)

        # When: fetching page 1 with page_size=2
        service = EntityListService()
        results, total = await service.list_entities(
            db_connection, EntityListParams(page=1, page_size=2)
        )

        # Then: 2 results returned but total >= 6
        assert len(results) == 2
        assert total >= 6
