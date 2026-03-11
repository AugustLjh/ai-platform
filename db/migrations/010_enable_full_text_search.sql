-- Enable PostgreSQL full-text search and reconcile pgvector usage
-- Migration: 010_enable_full_text_search.sql

-- Keep a generated full-text search vector in sync with title/content.
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS search_vector tsvector
GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', COALESCE(title, '')), 'A') ||
    setweight(to_tsvector('simple', COALESCE(content, '')), 'B')
) STORED;

CREATE INDEX IF NOT EXISTS idx_documents_search_vector_gin
ON documents USING gin (search_vector);

-- Ensure pgvector data exists in the dedicated vector column used by queries.
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS embedding_vector vector(384);

UPDATE documents
SET embedding_vector = embedding::vector
WHERE embedding IS NOT NULL
  AND embedding_vector IS NULL;

CREATE OR REPLACE FUNCTION sync_documents_embedding_vector()
RETURNS trigger AS $$
BEGIN
    IF NEW.embedding IS NULL THEN
        NEW.embedding_vector = NULL;
    ELSE
        NEW.embedding_vector = NEW.embedding::vector;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_sync_embedding_vector ON documents;

CREATE TRIGGER trg_documents_sync_embedding_vector
BEFORE INSERT OR UPDATE OF embedding ON documents
FOR EACH ROW
EXECUTE FUNCTION sync_documents_embedding_vector();

CREATE INDEX IF NOT EXISTS idx_documents_embedding_vector_ivfflat
ON documents USING ivfflat (embedding_vector vector_cosine_ops)
WITH (lists = 100);

COMMENT ON COLUMN documents.search_vector IS 'Generated full-text search vector for keyword retrieval';
COMMENT ON COLUMN documents.embedding_vector IS 'Vector embedding (pgvector type) used for semantic search';
