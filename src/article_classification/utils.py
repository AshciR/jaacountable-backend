"""Utility functions for classification results."""
from .models import ClassificationResult


def filter_relevant_classifications(
    results: list[ClassificationResult],
    min_confidence: float = 0.7
) -> list[ClassificationResult]:
    """
    Filter classification results to only relevant articles.

    An article is relevant if AT LEAST ONE classifier marks it as:
    - is_relevant = True
    - confidence >= min_confidence

    Args:
        results: Classification results from ClassificationService
        min_confidence: Minimum confidence threshold (default: 0.7)

    Returns:
        List of relevant classification results (may be empty)

    Example:
        >>> # Only store if relevant
        >>> relevant = filter_relevant_classifications(
        ...     results=classification_results,
        ...     min_confidence=0.7
        ... )
        >>> if relevant:
        ...     # Store article and classifications
        ...     pass
    """
    return [
        result
        for result in results
        if result.is_relevant and result.confidence >= min_confidence
    ]
