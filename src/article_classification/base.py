"""Base protocol for article classification strategies."""
from typing import Protocol
from dotenv import load_dotenv
from .models import ClassificationInput, ClassificationResult, NormalizedEntity

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


class EntityNormalizer(Protocol):
    """
    Protocol for entity normalization services using structural subtyping.

    This Protocol defines the interface for entity normalizers without requiring
    inheritance. Any class that implements the normalize() method with the correct
    signature can be used as an EntityNormalizer.

    Entity normalization converts raw entity names (with titles, variations, etc.)
    into canonical forms for consistency and deduplication across articles.

    Uses batch processing for efficiency (single LLM call for multiple entities).

    Example:
        class MyNormalizer:  # No inheritance needed!
            async def normalize(self, entities: list[str]) -> list[NormalizedEntity]:
                # Implementation here
                pass

        # MyNormalizer satisfies EntityNormalizer Protocol
    """

    async def normalize(
        self, entities: list[str]
    ) -> list[NormalizedEntity]:
        """
        Normalize a batch of entity names to canonical forms.

        Args:
            entities: List of original entity names to normalize.
                     Example: ["Hon. Ruel Reid", "OCG", "Ministry of Education"]

        Returns:
            List of NormalizedEntity objects with original/normalized pairs,
            per-entity confidence scores, and reasoning for each normalization.
            Example: [
                NormalizedEntity(
                    original_value="Hon. Ruel Reid",
                    normalized_value="ruel_reid",
                    confidence=0.95,
                    reason="Removed title 'Hon.' and standardized format"
                )
            ]

        Raises:
            ValueError: If entities list is empty or normalization fails
        """
        ...
