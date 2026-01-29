-- Add knowledge base enhancement fields
-- Migration: 002_knowledge_base_enhancements.sql

-- Add new fields to documents table
ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS access_level VARCHAR(20) NOT NULL DEFAULT 'tenant';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding FLOAT[];

-- Add indexes for new fields
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_access_level ON documents(access_level);
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type);

-- Add check constraint for access_level
ALTER TABLE documents DROP CONSTRAINT IF EXISTS check_access_level;
ALTER TABLE documents ADD CONSTRAINT check_access_level
    CHECK (access_level IN ('tenant', 'user'));

-- Add check constraint for source_type
ALTER TABLE documents DROP CONSTRAINT IF EXISTS check_source_type;
ALTER TABLE documents ADD CONSTRAINT check_source_type
    CHECK (source_type IN ('file', 'url', 'manual', 'batch'));

-- Optional: Install pgvector extension for better vector search performance
-- Uncomment if you want to use pgvector in the future
-- CREATE EXTENSION IF NOT EXISTS vector;
-- Then you can change: embedding FLOAT[] to embedding VECTOR(384)

COMMENT ON COLUMN documents.user_id IS 'User ID for private documents (null for tenant-level)';
COMMENT ON COLUMN documents.access_level IS 'Access control: tenant (public) or user (private)';
COMMENT ON COLUMN documents.embedding IS 'Vector embedding for semantic search';
