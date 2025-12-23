"""Classification models for article classification service."""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, field_validator, ConfigDict, Field


class ClassifierType(str, Enum):
    """
    Types of classifiers available for article analysis.

    Each classifier focuses on a specific accountability topic:
    - CORRUPTION: Detects corruption, contract irregularities, OCG investigations
    - HURRICANE_RELIEF: Tracks disaster relief fund allocation and management

    Example:
        >>> classifier_type = ClassifierType.CORRUPTION
        >>> classifier_type.value
        'CORRUPTION'
        >>> ClassifierType.HURRICANE_RELIEF
        <ClassifierType.HURRICANE_RELIEF: 'HURRICANE_RELIEF'>
    """

    CORRUPTION = "CORRUPTION"
    HURRICANE_RELIEF = "HURRICANE_RELIEF"


class ClassificationInput(BaseModel):
    """
    Input data for article classification agents.

    This model serves as the interface between the article extraction layer
    and the classification layer. It combines content from ExtractedArticleContent
    with contextual metadata from the scraper to provide all necessary information
    for AI-based relevance classification.

    Important: Classification happens BEFORE database storage, so article_id is
    not available at this stage. The URL serves as the unique identifier.

    Workflow:
        1. Extract article content from news source → ExtractedArticleContent
        2. Construct ClassificationInput (this model) from extraction + scraper context
        3. Classify to determine relevance → ClassificationResult
        4. If relevant, store article in database (article_id generated here)

    Example:
        >>> from datetime import datetime, timezone
        >>> # After extracting article content
        >>> url = "https://jamaica-gleaner.com/article/news/20251201/gov-announces-transparency"
        >>> section = "News"  # From scraper context
        >>> extracted = await extractor.extract(url)  # Returns ExtractedArticleContent
        >>>
        >>> # Construct classification input
        >>> classification_input = ClassificationInput(
        ...     url=url,
        ...     title=extracted.title,
        ...     section=section,
        ...     full_text=extracted.full_text,
        ...     published_date=extracted.published_date,
        ... )
        >>>
        >>> # Pass to classifier
        >>> result = await corruption_classifier.classify(classification_input)
        >>>
        >>> # Only store if relevant
        >>> if result.is_relevant:
        ...     # Store article and classification in database
        ...     pass
    """

    url: str
    title: str
    section: str
    full_text: str
    published_date: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate that url is not empty and has basic URL structure."""
        if not v or not v.strip():
            raise ValueError('URL cannot be empty')

        # Basic URL validation - must start with http:// or https://
        v = v.strip()
        if not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('URL must start with http:// or https://')

        return v

    @field_validator('title', 'section')
    @classmethod
    def validate_required_string(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()

    @field_validator('full_text')
    @classmethod
    def validate_full_text(cls, v: str) -> str:
        """Validate that full_text is not empty and meets minimum length."""
        if not v or not v.strip():
            raise ValueError('Full text cannot be empty')

        stripped = v.strip()
        # Minimum 50 characters for meaningful content
        if len(stripped) < 50:
            raise ValueError('Full text must be at least 50 characters')

        return stripped

    @field_validator('published_date')
    @classmethod
    def validate_published_date(cls, v: datetime | None) -> datetime | None:
        """Validate that published_date is timezone-aware if provided."""
        if v is None:
            return None

        # Ensure timezone-aware datetime (consistent with existing patterns)
        if v.tzinfo is None:
            raise ValueError('Published date must be timezone-aware')

        return v


class ClassificationResult(BaseModel):
    """
    Output from article classification agents.

    This model represents the structured result returned by classifier agents
    after analyzing an article for relevance to a specific accountability topic.
    The result includes a binary relevance decision, confidence score, reasoning
    for transparency, and optionally extracted key entities.

    Workflow Position:
        Extract → ClassificationInput → Classifier Agent → **ClassificationResult** → Database

    Mapping to Database (Classification model):
        - ClassificationResult.is_relevant → Threshold logic for storage decision
        - ClassificationResult.confidence → Classification.confidence_score
        - ClassificationResult.reasoning → Classification.reasoning
        - ClassificationResult.classifier_type → Classification.classifier_type
        - ClassificationResult.model_name → Classification.model_name
        - ClassificationResult.key_entities → Not currently stored (future enhancement)

    Example:
        >>> result = ClassificationResult(
        ...     is_relevant=True,
        ...     confidence=0.85,
        ...     reasoning="Article discusses OCG investigation into contract irregularities at Ministry of Education",
        ...     key_entities=["OCG", "Ministry of Education", "Contract Irregularities"],
        ...     classifier_type=ClassifierType.CORRUPTION,
        ...     model_name="gpt-4o-mini"
        ... )
        >>> result.is_relevant
        True
        >>> result.key_entities
        ['OCG', 'Ministry of Education', 'Contract Irregularities']
        >>> result.model_name
        'gpt-4o-mini'
    """

    is_relevant: bool
    confidence: float
    reasoning: str
    key_entities: list[str] = []
    classifier_type: ClassifierType
    model_name: str

    model_config = ConfigDict(from_attributes=True)

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Validate that confidence is between 0.0 and 1.0."""
        if v < 0.0 or v > 1.0:
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v

    @field_validator('reasoning', 'model_name')
    @classmethod
    def validate_required_string(cls, v: str) -> str:
        """Validate that required string fields are not empty."""
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()

    @field_validator('key_entities')
    @classmethod
    def validate_key_entities(cls, v: list[str]) -> list[str]:
        """Validate and clean each entity in the list."""
        if not isinstance(v, list):
            raise ValueError('Key entities must be a list')

        # Strip whitespace from each entity and filter out empty strings
        cleaned = [entity.strip() for entity in v if entity and entity.strip()]
        return cleaned


class EntityNormalizationInput(BaseModel):
    """
    Input schema for entity normalization agent tool.

    This model defines the contract for the entity_normalizer tool that can be
    called by classification agents to normalize entity names during classification.

    The normalization tool uses AI to convert raw entity names (with titles, variations,
    etc.) into canonical forms with underscores for consistency across articles.

    Example:
        >>> input_data = EntityNormalizationInput(
        ...     entity_names=["Hon. Ruel Reid", "OCG", "Min. of Education"],
        ...     article_context="corruption investigation"
        ... )
        >>> # Agent tool will normalize these to: ["ruel_reid", "ocg", "ministry_of_education"]
    """

    entity_names: list[str] = Field(
        ...,
        description="List of raw entity names to normalize"
    )
    article_context: str = Field(
        default="",
        description="Context about the article (optional)"
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator('entity_names')
    @classmethod
    def validate_entity_names(cls, v: list[str]) -> list[str]:
        """Validate and clean entity names list."""
        if not v:
            raise ValueError('entity_names cannot be empty')

        # Strip whitespace from each entity and filter out empty strings
        cleaned = [name.strip() for name in v if name and name.strip()]

        if not cleaned:
            raise ValueError('entity_names must contain at least one non-empty name')

        return cleaned


class EntityNormalizationResult(BaseModel):
    """
    Output schema for entity normalization agent tool.

    This model represents the structured result returned by the entity_normalizer
    tool after normalizing a list of entity names. It provides a mapping from
    original names to normalized forms, along with confidence and notes.

    Normalization Rules Applied:
        - Lowercase everything
        - Remove titles (Mr., Hon., Minister, etc.)
        - Replace spaces with underscores
        - Preserve full names for people (e.g., "ruel_reid" not "reid")
        - Preserve acronyms (e.g., "OCG" → "ocg")
        - Standardize government entities

    Example:
        >>> result = EntityNormalizationResult(
        ...     normalized_entities={
        ...         "Hon. Ruel Reid": "ruel_reid",
        ...         "OCG": "ocg",
        ...         "Ministry of Education": "ministry_of_education"
        ...     },
        ...     confidence=0.95,
        ...     notes="All entities normalized successfully",
        ...     model_name="gpt-5-nano"
        ... )
        >>> result.normalized_entities["Hon. Ruel Reid"]
        'ruel_reid'
        >>> result.confidence
        0.95
    """

    normalized_entities: dict[str, str] = Field(
        ...,
        description="Mapping of original name → normalized name"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence score"
    )
    notes: str = Field(
        default="",
        description="Additional notes about normalization"
    )
    model_name: str = Field(
        ...,
        description="Model used for normalization"
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Validate that confidence is between 0.0 and 1.0."""
        if v < 0.0 or v > 1.0:
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v

    @field_validator('notes')
    @classmethod
    def validate_notes(cls, v: str) -> str:
        """Strip whitespace from notes."""
        return v.strip() if v else ""

    @field_validator('normalized_entities')
    @classmethod
    def validate_normalized_entities(cls, v: dict[str, str]) -> dict[str, str]:
        """Validate and clean normalized entities mapping."""
        if not isinstance(v, dict):
            raise ValueError('normalized_entities must be a dictionary')

        # Ensure all keys and values are stripped and non-empty
        cleaned = {}
        for key, value in v.items():
            if not key or not key.strip():
                raise ValueError('normalized_entities keys cannot be empty')
            if not value or not value.strip():
                raise ValueError('normalized_entities values cannot be empty')

            cleaned[key.strip()] = value.strip()

        return cleaned
