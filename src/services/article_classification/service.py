"""Classification service that orchestrates article classification."""
from .base import ArticleClassifier
from .models import ClassificationInput, ClassificationResult


class ClassificationService:
    """
    Service that orchestrates article classification using injected classifier.

    This service provides a unified interface for classification and enables
    dependency injection for testing and extensibility.

    Usage:
        # With coordinator adapter
        from classification_coordinator_agent.adapter import ClassificationCoordinatorAdapter

        classifier = ClassificationCoordinatorAdapter()
        service = ClassificationService(classifier=classifier)

        # Classify article
        article = ClassificationInput(
            url="https://example.com/article",
            title="Article Title",
            section="news",
            full_text="Article content..."
        )
        result = await service.classify(article)

        if result.is_relevant and result.confidence >= 0.7:
            # Store article and classification
            pass
    """

    def __init__(self, classifier: ArticleClassifier):
        """
        Initialize classification service.

        Args:
            classifier: Classifier instance implementing ArticleClassifier Protocol
        """
        self.classifier = classifier

    async def classify(
        self, article: ClassificationInput
    ) -> ClassificationResult:
        """
        Classify article using injected classifier.

        Args:
            article: Article data with url, title, section, full_text, etc.

        Returns:
            ClassificationResult with relevance decision, confidence, reasoning, etc.

        Raises:
            ValueError: If article data is invalid or classification fails
        """
        return await self.classifier.classify(article)
