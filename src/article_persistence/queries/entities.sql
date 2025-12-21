-- name: find_entity_by_normalized_name^
-- Find entity by normalized name (for deduplication checks)
SELECT id, name, normalized_name, created_at
FROM entities
WHERE normalized_name = :normalized_name;

-- name: insert_entity<!
-- Insert new entity and return with generated id
INSERT INTO entities (name, normalized_name, created_at)
VALUES (:name, :normalized_name, :created_at)
RETURNING id, name, normalized_name, created_at;

-- name: find_entities_by_article_id
-- Find all entities linked to a specific article
SELECT e.id, e.name, e.normalized_name, e.created_at
FROM entities e
JOIN article_entities ae ON e.id = ae.entity_id
WHERE ae.article_id = :article_id
ORDER BY e.name;

-- name: find_article_ids_by_entity_id
-- Find all article IDs linked to a specific entity
SELECT article_id
FROM article_entities
WHERE entity_id = :entity_id
ORDER BY article_id;
