-- Add chunk-level indexing and improve keyword search for CJK content.
-- Migration: 011_document_chunk_indexing.sql

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS search_terms TEXT NOT NULL DEFAULT '';

DROP INDEX IF EXISTS idx_documents_search_vector_gin;
ALTER TABLE documents DROP COLUMN IF EXISTS search_vector;

ALTER TABLE documents
ADD COLUMN search_vector tsvector
GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', COALESCE(title, '')), 'A') ||
    setweight(to_tsvector('simple', COALESCE(content, '')), 'B') ||
    setweight(to_tsvector('simple', COALESCE(search_terms, '')), 'A')
) STORED;

CREATE INDEX IF NOT EXISTS idx_documents_search_vector_gin
ON documents USING gin (search_vector);

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    access_level VARCHAR(20) NOT NULL DEFAULT 'tenant',
    chunk_index INTEGER NOT NULL,
    start_offset INTEGER NOT NULL DEFAULT 0,
    end_offset INTEGER NOT NULL DEFAULT 0,
    char_count INTEGER NOT NULL DEFAULT 0,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    source VARCHAR(255),
    source_type VARCHAR(50),
    embedding_model VARCHAR(100),
    embedding FLOAT[],
    embedding_vector vector(384),
    search_terms TEXT NOT NULL DEFAULT '',
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', COALESCE(title, '')), 'A') ||
        setweight(to_tsvector('simple', COALESCE(content, '')), 'B') ||
        setweight(to_tsvector('simple', COALESCE(search_terms, '')), 'A')
    ) STORED,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_document_chunks_document_chunk UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_id ON document_chunks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_knowledge_base_id ON document_chunks(knowledge_base_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_access_level ON document_chunks(access_level);
CREATE INDEX IF NOT EXISTS idx_document_chunks_source_type ON document_chunks(source_type);
CREATE INDEX IF NOT EXISTS idx_document_chunks_chunk_index ON document_chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_document_chunks_search_vector_gin
ON document_chunks USING gin (search_vector);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_vector_ivfflat
ON document_chunks USING ivfflat (embedding_vector vector_cosine_ops)
WITH (lists = 100);

CREATE OR REPLACE FUNCTION sync_document_chunks_embedding_vector()
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

DROP TRIGGER IF EXISTS trg_document_chunks_sync_embedding_vector ON document_chunks;

CREATE TRIGGER trg_document_chunks_sync_embedding_vector
BEFORE INSERT OR UPDATE OF embedding ON document_chunks
FOR EACH ROW
EXECUTE FUNCTION sync_document_chunks_embedding_vector();

INSERT INTO document_chunks (
    document_id,
    tenant_id,
    knowledge_base_id,
    user_id,
    access_level,
    chunk_index,
    start_offset,
    end_offset,
    char_count,
    title,
    content,
    source,
    source_type,
    embedding_model,
    embedding,
    embedding_vector,
    search_terms,
    metadata,
    created_at,
    updated_at
)
SELECT
    d.id,
    d.tenant_id,
    d.knowledge_base_id,
    d.user_id,
    d.access_level,
    1,
    0,
    char_length(COALESCE(d.content, '')),
    char_length(COALESCE(d.content, '')),
    d.title,
    d.content,
    d.source,
    d.source_type,
    d.embedding_model,
    d.embedding,
    d.embedding_vector,
    d.search_terms,
    jsonb_build_object('is_legacy_full_document_chunk', true),
    d.created_at,
    d.updated_at
FROM documents d
WHERE NOT EXISTS (
    SELECT 1
    FROM document_chunks dc
    WHERE dc.document_id = d.id
);

COMMENT ON TABLE document_chunks IS 'Chunk-level retrieval index for knowledge base documents';
COMMENT ON COLUMN document_chunks.search_terms IS 'Pre-tokenized search terms to improve CJK keyword recall';
COMMENT ON COLUMN documents.search_terms IS 'Pre-tokenized search terms to improve CJK keyword recall';
