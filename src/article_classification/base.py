"""Base protocol for article classification strategies."""
from typing import Protocol
from dotenv import load_dotenv
from .models import ClassificationInput, ClassificationResult

# Load environment variables from .env file
load_dotenv()

APP_NAME = "jaccountable_backend"
CLASSIFICATION_MODEL = "gpt-5-nano"
NORMALIZATION_MODEL = "gpt-5-nano"

class ArticleClassifier(Protocol):
    """
    Protocol for article classification strategies using structural subtyping.

    This Protocol defines the interface for article classifiers without
    requiring inheritance. Any class that implements the classify() method
    with the correct signature can be used as an ArticleClassifier.

    This enables the Strategy Pattern with maximum flexibility:
    - No need to inherit from a base class
    - Duck typing with type safety
    - Easy to add new classifiers
    - Adapts Google ADK agents to a consistent interface

    Example:
        class MyClassifier:  # No inheritance needed!
            async def classify(self, article: ClassificationInput) -> ClassificationResult:
                # Implementation here
                pass

        # MyClassifier satisfies ArticleClassifier Protocol
    """

    async def classify(
        self, article: ClassificationInput
    ) -> ClassificationResult:
        """
        Classify an article for relevance to a specific topic.

        Args:
            article: Article data with url, title, section, full_text, and
                    optional published_date.

        Returns:
            ClassificationResult with is_relevant (true/false), confidence,
            reasoning, key_entities, classifier_type, and model_name.

        Raises:
            ValueError: If article data is invalid or classification fails
        """
        ...
