-- name: insert_article_entity<!
-- Link article to entity with classifier type
INSERT INTO article_entities (article_id, entity_id, classifier_type, created_at)
VALUES (:article_id, :entity_id, :classifier_type, :created_at)
RETURNING id, article_id, entity_id, classifier_type, created_at;
