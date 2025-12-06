-- name: insert_classification<!
-- Insert a new classification and return the classification record
INSERT INTO classifications (
    article_id,
    classifier_type,
    confidence_score,
    reasoning,
    classified_at,
    model_name,
    is_verified,
    verified_at,
    verified_by
)
VALUES (
    :article_id,
    :classifier_type,
    :confidence_score,
    :reasoning,
    :classified_at,
    :model_name,
    :is_verified,
    :verified_at,
    :verified_by
)
RETURNING id, article_id, classifier_type, confidence_score, reasoning,
          classified_at, model_name, is_verified, verified_at, verified_by;
