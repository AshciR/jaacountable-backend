"""Classification service that orchestrates article classification."""
import asyncio

from .base import ArticleClassifier
from .models import ClassificationInput, ClassificationResult


class ClassificationService:
    """
    Service that orchestrates article classification using multiple classifiers.

    This service runs all classifiers in parallel and returns all results,
    enabling multi-label classification. For example, an article about
    "government misuses hurricane relief funds" will be classified by both
    the corruption classifier AND the hurricane relief classifier.

    Usage:
        # With multiple classifiers
        from src.article_classification.agents import CorruptionClassifierAdapter

        corruption_classifier = CorruptionClassifierAdapter()
        # hurricane_classifier = HurricaneReliefClassifierAdapter()  # Future

        service = ClassificationService(classifiers=[corruption_classifier])

        # Classify article
        article = ClassificationInput(
            url="https://example.com/article",
            title="OCG Probes Hurricane Relief Fund Misuse",
            section="news",
            full_text="The Office of the Contractor General has launched..."
        )
        results = await service.classify(article)

        # Store relevant classifications
        for result in results:
            if result.is_relevant and result.confidence >= 0.7:
                # Store classification in database
                pass
    """

    def __init__(self, classifiers: list[ArticleClassifier]):
        """
        Initialize classification service with multiple classifiers.

        Args:
            classifiers: List of classifier instances implementing ArticleClassifier Protocol
        """
        self.classifiers = classifiers

    async def classify(
        self, article: ClassificationInput
    ) -> list[ClassificationResult]:
        """
        Classify article using all classifiers in parallel.

        Runs all classifiers concurrently to enable multi-label classification.
        Each classifier independently determines relevance.

        Args:
            article: Article data with url, title, section, full_text, etc.

        Returns:
            List of ClassificationResults from all classifiers. Each result
            includes is_relevant (true/false), confidence, reasoning, etc.
            Empty list if no classifiers configured.

        Raises:
            ValueError: If article data is invalid
        """
        if not self.classifiers:
            return []

        # Run all classifiers in parallel
        results = await asyncio.gather(
            *[classifier.classify(article) for classifier in self.classifiers],
            return_exceptions=True,
        )

        # Filter out exceptions (but log them)
        classified_results = []
        for result in results:
            if isinstance(result, Exception):
                # TODO: Add proper logging
                # For now, just skip failed classifiers
                continue
            classified_results.append(result)

        return classified_results
