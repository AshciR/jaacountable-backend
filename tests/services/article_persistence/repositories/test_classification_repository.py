"""Tests for ClassificationRepository."""

import asyncpg
import pytest
from datetime import datetime, timedelta, timezone

from src.article_persistence.repositories.classification_repository import ClassificationRepository
from src.article_persistence.models.domain import Classification
from tests.services.article_persistence.repositories.utils import create_test_article




class TestInsertClassificationHappyPath:
    """Happy path tests for insert_classification."""
    async def test_insert_classification_success(
            self,
            db_connection: asyncpg.Connection,
    ):
        # Given: an article exists and a valid classification with all fields populated
        inserted_article = await create_test_article(db_connection)

        classification = Classification(
            article_id=inserted_article.id,
            classifier_type="accountability",
            confidence_score=0.85,
            reasoning="Article discusses government spending",
            model_name="gpt-4o-mini",
            is_verified=True,
            verified_at=datetime(2025, 11, 20, 12, 0, 0, tzinfo=timezone.utc),
            verified_by="admin@example.com",
        )
        repository = ClassificationRepository()

        # When: the classification is inserted
        result = await repository.insert_classification(db_connection, classification)

        # Then: the returned classification has a database-generated id and matching fields
        assert result.id is not None
        assert result.article_id == inserted_article.id
        assert result.classifier_type == "accountability"
        assert result.confidence_score == 0.85
        assert result.reasoning == "Article discusses government spending"
        assert result.model_name == "gpt-4o-mini"
        assert result.is_verified is True
        assert result.verified_at == datetime(2025, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
        assert result.verified_by == "admin@example.com"

    async def test_insert_classification_with_minimal_fields(
            self,
            db_connection: asyncpg.Connection,
    ):
        # Given: an article exists and a classification with only required fields
        inserted_article = await create_test_article(
            db_connection, url="https://example.com/minimal-classification"
        )

        classification = Classification(
            article_id=inserted_article.id,
            classifier_type="accountability",
            confidence_score=0.75,
            model_name="gpt-4o-mini",
        )
        repository = ClassificationRepository()

        # When: the classification is inserted
        result = await repository.insert_classification(db_connection, classification)

        # Then: returns classification with id, defaults applied, optional fields are None
        assert result.id is not None
        assert result.article_id == inserted_article.id
        assert result.classifier_type == "accountability"
        assert result.confidence_score == 0.75
        assert result.model_name == "gpt-4o-mini"
        assert result.reasoning is None
        assert result.is_verified is False
        assert result.verified_at is None
        assert result.verified_by is None
        assert result.classified_at is not None

    async def test_insert_classification_defaults_classified_at(
            self,
            db_connection: asyncpg.Connection,
    ):
        # Given: a classification without explicit classified_at
        inserted_article = await create_test_article(
            db_connection, url="https://example.com/default-classified-at"
        )

        before_insert = datetime.now(timezone.utc)
        classification = Classification(
            article_id=inserted_article.id,
            classifier_type="accountability",
            confidence_score=0.5,
            model_name="gpt-4o-mini",
        )
        repository = ClassificationRepository()

        # When: the classification is inserted
        result = await repository.insert_classification(db_connection, classification)
        after_insert = datetime.now(timezone.utc)

        # Then: classified_at is close to current time
        assert result.id is not None
        assert result.classified_at is not None
        # Allow 1 second tolerance for test execution time
        assert before_insert - timedelta(seconds=1) <= result.classified_at <= after_insert + timedelta(seconds=1)

    async def test_insert_multiple_classifications_for_same_article(
            self,
            db_connection: asyncpg.Connection,
    ):
        # Given: an article exists
        inserted_article = await create_test_article(
            db_connection, url="https://example.com/multiple-classifications"
        )
        repository = ClassificationRepository()

        # When: multiple classifications are inserted for the same article
        classifications = [
            Classification(
                article_id=inserted_article.id,
                classifier_type="accountability",
                confidence_score=0.9,
                model_name="gpt-4o-mini",
            ),
            Classification(
                article_id=inserted_article.id,
                classifier_type="sentiment",
                confidence_score=0.7,
                model_name="gpt-4o",
            ),
        ]

        results = []
        for classification in classifications:
            result = await repository.insert_classification(db_connection, classification)
            results.append(result)

        # Then: each gets unique id and correct data
        assert len(results) == 2
        assert results[0].id != results[1].id
        assert results[0].classifier_type == "accountability"
        assert results[1].classifier_type == "sentiment"

    async def test_insert_classification_strips_whitespace(
            self,
            db_connection: asyncpg.Connection,
    ):
        # Given: a classification with whitespace-padded fields
        inserted_article = await create_test_article(
            db_connection, url="https://example.com/whitespace-classification"
        )

        classification = Classification(
            article_id=inserted_article.id,
            classifier_type="  accountability  ",
            confidence_score=0.5,
            model_name="  gpt-4o-mini  ",
        )
        repository = ClassificationRepository()

        # When: the classification is inserted
        result = await repository.insert_classification(db_connection, classification)

        # Then: returns classification with trimmed fields (Pydantic validation)
        assert result.id is not None
        assert result.classifier_type == "accountability"
        assert result.model_name == "gpt-4o-mini"


class TestInsertClassificationDatabaseConstraints:
    """Database constraint tests for insert_classification."""
    async def test_invalid_article_id_raises_foreign_key_violation(
            self,
            db_connection: asyncpg.Connection,
    ):
        # Given: a classification referencing non-existent article_id
        classification = Classification(
            article_id=99999,  # Non-existent article ID
            classifier_type="accountability",
            confidence_score=0.5,
            model_name="gpt-4o-mini",
        )
        repository = ClassificationRepository()

        # When: the classification is inserted
        # Then: raises asyncpg.ForeignKeyViolationError
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await repository.insert_classification(db_connection, classification)

    async def test_cascade_delete_removes_classification_when_article_deleted(
            self,
            db_connection: asyncpg.Connection,
    ):
        # Given: an article with a classification
        inserted_article = await create_test_article(
            db_connection, url="https://example.com/cascade-delete-test"
        )

        classification = Classification(
            article_id=inserted_article.id,
            classifier_type="accountability",
            confidence_score=0.5,
            model_name="gpt-4o-mini",
        )
        classification_repo = ClassificationRepository()
        inserted_classification = await classification_repo.insert_classification(
            db_connection, classification
        )

        # When: the article is deleted
        await db_connection.execute(
            "DELETE FROM articles WHERE id = $1", inserted_article.id
        )

        # Then: the classification is also deleted (cascade)
        result = await db_connection.fetchval(
            "SELECT COUNT(*) FROM classifications WHERE id = $1",
            inserted_classification.id,
        )
        assert result == 0


class TestInsertClassificationEdgeCases:
    """Edge case tests for insert_classification."""
    async def test_confidence_score_at_zero_boundary(
            self,
            db_connection: asyncpg.Connection,
    ):
        # Given: a classification with confidence_score exactly 0.0
        inserted_article = await create_test_article(
            db_connection, url="https://example.com/zero-confidence"
        )

        classification = Classification(
            article_id=inserted_article.id,
            classifier_type="accountability",
            confidence_score=0.0,
            model_name="gpt-4o-mini",
        )
        repository = ClassificationRepository()

        # When: the classification is inserted
        result = await repository.insert_classification(db_connection, classification)

        # Then: successfully inserts with confidence_score = 0.0
        assert result.id is not None
        assert result.confidence_score == 0.0

    async def test_confidence_score_at_one_boundary(
            self,
            db_connection: asyncpg.Connection,
    ):
        # Given: a classification with confidence_score exactly 1.0
        inserted_article = await create_test_article(
            db_connection, url="https://example.com/full-confidence"
        )

        classification = Classification(
            article_id=inserted_article.id,
            classifier_type="accountability",
            confidence_score=1.0,
            model_name="gpt-4o-mini",
        )
        repository = ClassificationRepository()

        # When: the classification is inserted
        result = await repository.insert_classification(db_connection, classification)

        # Then: successfully inserts with confidence_score = 1.0
        assert result.id is not None
        assert result.confidence_score == 1.0

    async def test_with_unicode_in_reasoning(
            self,
            db_connection: asyncpg.Connection,
    ):
        # Given: a classification with Unicode characters in reasoning
        inserted_article = await create_test_article(
            db_connection, url="https://example.com/unicode-reasoning"
        )

        unicode_reasoning = "Article discusses café prices — 日本語テスト émojis 🎉"
        classification = Classification(
            article_id=inserted_article.id,
            classifier_type="accountability",
            confidence_score=0.5,
            reasoning=unicode_reasoning,
            model_name="gpt-4o-mini",
        )
        repository = ClassificationRepository()

        # When: the classification is inserted
        result = await repository.insert_classification(db_connection, classification)

        # Then: returns classification with Unicode reasoning preserved
        assert result.id is not None
        assert result.reasoning == unicode_reasoning

    async def test_with_custom_classified_at(
            self,
            db_connection: asyncpg.Connection,
    ):
        # Given: a classification with explicit classified_at value
        inserted_article = await create_test_article(
            db_connection, url="https://example.com/custom-classified-at"
        )

        custom_classified_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        classification = Classification(
            article_id=inserted_article.id,
            classifier_type="accountability",
            confidence_score=0.5,
            model_name="gpt-4o-mini",
            classified_at=custom_classified_at,
        )
        repository = ClassificationRepository()

        # When: the classification is inserted
        result = await repository.insert_classification(db_connection, classification)

        # Then: returns classification with custom classified_at preserved
        assert result.id is not None
        assert result.classified_at == custom_classified_at


