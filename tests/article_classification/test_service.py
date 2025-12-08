"""Tests for ClassificationService."""
import asyncio
import time

import pytest

from src.article_classification.models import (
    ClassificationInput,
    ClassificationResult,
    ClassifierType,
)
from src.article_classification.service import ClassificationService


class MockCorruptionClassifier:
    """Mock corruption classifier for testing parallel execution."""

    async def classify(self, article: ClassificationInput) -> ClassificationResult:
        """Returns a mock corruption classification result."""
        return ClassificationResult(
            is_relevant=True,
            confidence=0.9,
            reasoning="OCG investigation",
            key_entities=["OCG"],
            classifier_type=ClassifierType.CORRUPTION,
            model_name="mock-corruption",
        )


class MockHurricaneClassifier:
    """Mock hurricane classifier for testing parallel execution."""

    async def classify(self, article: ClassificationInput) -> ClassificationResult:
        """Returns a mock hurricane classification result."""
        return ClassificationResult(
            is_relevant=True,
            confidence=0.85,
            reasoning="Hurricane relief fund allocation",
            key_entities=["NEMA", "Ministry of Local Government"],
            classifier_type=ClassifierType.HURRICANE_RELIEF,
            model_name="mock-hurricane",
        )


class SlowClassifier:
    """Mock classifier with configurable delay for parallelism testing."""

    def __init__(self, classifier_type: ClassifierType, wait_time: float = 0.1):
        """
        Initialize slow classifier.

        Args:
            classifier_type: Type of classifier (CORRUPTION, HURRICANE_RELIEF, etc.)
            wait_time: Seconds to wait during classify() to simulate slow LLM call
        """
        self.classifier_type = classifier_type
        self.wait_time = wait_time

    async def classify(self, article: ClassificationInput) -> ClassificationResult:
        """Simulate slow LLM call with configurable delay."""
        await asyncio.sleep(self.wait_time)
        return ClassificationResult(
            is_relevant=True,
            confidence=0.8,
            reasoning="Test",
            classifier_type=self.classifier_type,
            model_name="slow-model",
        )


class FailingClassifier:
    """Mock classifier that always raises an exception."""

    def __init__(self, error_message: str = "Classifier failed"):
        """
        Initialize failing classifier.

        Args:
            error_message: Custom error message for the exception
        """
        self.error_message = error_message

    async def classify(self, article: ClassificationInput) -> ClassificationResult:
        """Always raises ValueError."""
        raise ValueError(self.error_message)


@pytest.fixture
def mock_corruption_classifier() -> MockCorruptionClassifier:
    """Mock corruption classifier."""
    return MockCorruptionClassifier()


@pytest.fixture
def mock_hurricane_classifier() -> MockHurricaneClassifier:
    """Mock hurricane classifier."""
    return MockHurricaneClassifier()


@pytest.fixture
def failing_classifier() -> FailingClassifier:
    """Mock classifier that raises exception."""
    return FailingClassifier()


class TestClassificationServiceMultipleClassifiers:
    """Test service with multiple classifiers running in parallel."""

    async def test_runs_two_classifiers_in_parallel_returns_both_results(
        self,
        sample_corruption_article: ClassificationInput,
        mock_corruption_classifier: MockCorruptionClassifier,
        mock_hurricane_classifier: MockHurricaneClassifier,
    ):
        # Given: Service with corruption + hurricane classifiers
        service = ClassificationService(
            classifiers=[mock_corruption_classifier, mock_hurricane_classifier]
        )

        # When: Classifying an article
        results = await service.classify(sample_corruption_article)

        # Then: Returns 2 results with correct classifier types
        assert len(results) == 2

        corruption_result = next(
            r for r in results if r.classifier_type == ClassifierType.CORRUPTION
        )
        hurricane_result = next(
            r for r in results if r.classifier_type == ClassifierType.HURRICANE_RELIEF
        )

        assert corruption_result.is_relevant is True
        assert corruption_result.confidence == 0.9
        assert hurricane_result.is_relevant is True
        assert hurricane_result.confidence == 0.85

    async def test_runs_three_classifiers_in_parallel_returns_all_results(
        self,
        sample_corruption_article: ClassificationInput,
        mock_corruption_classifier: MockCorruptionClassifier,
        mock_hurricane_classifier: MockHurricaneClassifier,
    ):
        # Given: Service with 3 classifiers (create third classifier with slow wait time)
        third_classifier = SlowClassifier(
            classifier_type=ClassifierType.CORRUPTION, wait_time=0.0
        )

        service = ClassificationService(
            classifiers=[
                mock_corruption_classifier,
                mock_hurricane_classifier,
                third_classifier,
            ]
        )

        # When: Classifying an article
        results = await service.classify(sample_corruption_article)

        # Then: Returns 3 results
        assert len(results) == 3

    async def test_classifiers_run_in_parallel_not_sequentially(
        self, sample_corruption_article: ClassificationInput
    ):
        """Verify classifiers actually run in parallel, not sequentially."""
        # Given: Two classifiers that each take 0.1 seconds
        classifier1 = SlowClassifier(ClassifierType.CORRUPTION, wait_time=0.1)
        classifier2 = SlowClassifier(ClassifierType.HURRICANE_RELIEF, wait_time=0.1)

        service = ClassificationService(classifiers=[classifier1, classifier2])

        # When: Classifying article
        start = time.time()
        results = await service.classify(sample_corruption_article)
        elapsed = time.time() - start

        # Then: Total time is ~0.1s (parallel), not ~0.2s (sequential)
        assert len(results) == 2
        assert elapsed < 0.15  # Should be ~0.1s if parallel, ~0.2s if sequential


class TestClassificationServiceErrorHandling:
    """Test exception handling when classifiers fail."""

    async def test_one_classifier_fails_other_succeeds_returns_successful_result(
        self,
        sample_corruption_article: ClassificationInput,
        mock_corruption_classifier: MockCorruptionClassifier,
        failing_classifier: FailingClassifier,
    ):
        # Given: Service with one failing classifier and one working classifier
        service = ClassificationService(
            classifiers=[failing_classifier, mock_corruption_classifier]
        )

        # When: Classifying an article
        results = await service.classify(sample_corruption_article)

        # Then: Returns 1 result (from successful classifier), skips exception
        assert len(results) == 1
        assert results[0].classifier_type == ClassifierType.CORRUPTION
        assert results[0].is_relevant is True

    async def test_all_classifiers_fail_returns_empty_list(
        self,
        sample_corruption_article: ClassificationInput,
        failing_classifier: FailingClassifier,
    ):
        # Given: Service with two failing classifiers
        failing_classifier_2 = FailingClassifier("Second classifier failed")

        service = ClassificationService(
            classifiers=[failing_classifier, failing_classifier_2]
        )

        # When: Classifying an article
        results = await service.classify(sample_corruption_article)

        # Then: Returns empty list
        assert len(results) == 0

    async def test_logs_classifier_failure_with_details(
        self,
        sample_corruption_article: ClassificationInput,
        failing_classifier: FailingClassifier,
        caplog: pytest.LogCaptureFixture,
    ):
        # Given: Service with failing classifier
        service = ClassificationService(classifiers=[failing_classifier])

        # When: Classifying an article
        await service.classify(sample_corruption_article)

        # Then: Logger warning called with classifier name, URL, and exception
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert log_record.levelname == "WARNING"
        assert "FailingClassifier" in log_record.message  # Classifier name
        assert sample_corruption_article.url in log_record.message
        assert "ValueError" in log_record.message
        assert "Classifier failed" in log_record.message


class TestClassificationServiceEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_empty_classifier_list_returns_empty_results(
        self, sample_corruption_article: ClassificationInput
    ):
        # Given: Service with empty classifiers list
        service = ClassificationService(classifiers=[])

        # When: Classifying an article
        results = await service.classify(sample_corruption_article)

        # Then: Returns empty list immediately
        assert len(results) == 0

    async def test_single_classifier_returns_single_result(
        self,
        sample_corruption_article: ClassificationInput,
        mock_corruption_classifier: MockCorruptionClassifier,
    ):
        # Given: Service with only one classifier
        service = ClassificationService(classifiers=[mock_corruption_classifier])

        # When: Classifying an article
        results = await service.classify(sample_corruption_article)

        # Then: Returns 1 result
        assert len(results) == 1
        assert results[0].classifier_type == ClassifierType.CORRUPTION
