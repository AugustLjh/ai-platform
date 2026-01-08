-- Enable pgvector extension and optimize vector search
-- Migration: 003_enable_pgvector.sql
--
-- NOTE: This migration is OPTIONAL. Only run if you want to use pgvector for better performance.
-- To use this, you need to:
-- 1. Install pgvector extension: https://github.com/pgvector/pgvector
-- 2. Set USE_PGVECTOR=true in your environment variables

-- Install pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Convert embedding column to vector type
-- First, create a new column
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_vector vector(384);

-- Copy data from existing embedding column (if exists)
UPDATE documents
SET embedding_vector = embedding::vector
WHERE embedding IS NOT NULL AND embedding_vector IS NULL;

-- Optional: Drop old column and rename new one
-- Only do this after verifying data is correct
-- ALTER TABLE documents DROP COLUMN IF EXISTS embedding;
-- ALTER TABLE documents RENAME COLUMN embedding_vector TO embedding;

-- Create index for fast vector search
-- IVFFlat index: good for datasets > 10k vectors
CREATE INDEX IF NOT EXISTS idx_documents_embedding_vector_ivfflat
ON documents USING ivfflat (embedding_vector vector_cosine_ops)
WITH (lists = 100);

-- Alternative: HNSW index (better quality, slower build)
-- CREATE INDEX IF NOT EXISTS idx_documents_embedding_vector_hnsw
-- ON documents USING hnsw (embedding_vector vector_cosine_ops);

-- Add comment
COMMENT ON COLUMN documents.embedding_vector IS 'Vector embedding (pgvector type) for semantic search';

-- Performance tips displayed
DO $$
BEGIN
    RAISE NOTICE '=================================================================';
    RAISE NOTICE 'pgvector extension installed successfully!';
    RAISE NOTICE '=================================================================';
    RAISE NOTICE 'Performance Tips:';
    RAISE NOTICE '1. Set USE_PGVECTOR=true in environment';
    RAISE NOTICE '2. For best IVFFlat performance, tune lists parameter:';
    RAISE NOTICE '   - Small datasets (<10k): lists = 100';
    RAISE NOTICE '   - Medium datasets (10k-100k): lists = 200-500';
    RAISE NOTICE '   - Large datasets (>100k): lists = sqrt(total_vectors)';
    RAISE NOTICE '3. HNSW index provides better quality but slower build time';
    RAISE NOTICE '4. Monitor query performance: EXPLAIN ANALYZE SELECT ...';
    RAISE NOTICE '=================================================================';
END $$;
