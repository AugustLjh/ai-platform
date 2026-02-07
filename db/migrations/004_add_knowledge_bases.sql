-- Add knowledge bases table and update documents table
-- Migration: 004_add_knowledge_bases.sql
-- This migration creates a hierarchical structure where knowledge bases are containers for documents

-- Create knowledge_bases table
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    access_level VARCHAR(20) NOT NULL DEFAULT 'tenant',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    CONSTRAINT check_kb_access_level CHECK (access_level IN ('tenant', 'user'))
);

-- Create indexes for knowledge_bases table
CREATE INDEX idx_knowledge_bases_tenant_id ON knowledge_bases(tenant_id);
CREATE INDEX idx_knowledge_bases_user_id ON knowledge_bases(user_id);
CREATE INDEX idx_knowledge_bases_access_level ON knowledge_bases(access_level);
CREATE INDEX idx_knowledge_bases_created_at ON knowledge_bases(created_at DESC);
CREATE INDEX idx_knowledge_bases_name ON knowledge_bases(name);

-- Add trigger for updated_at on knowledge_bases
CREATE TRIGGER update_knowledge_bases_updated_at
    BEFORE UPDATE ON knowledge_bases
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add knowledge_base_id foreign key to documents table
ALTER TABLE documents ADD COLUMN IF NOT EXISTS knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE;

-- Create index for the foreign key
CREATE INDEX IF NOT EXISTS idx_documents_knowledge_base_id ON documents(knowledge_base_id);

-- Add comments for documentation
COMMENT ON TABLE knowledge_bases IS 'Stores knowledge base containers that organize documents';
COMMENT ON COLUMN knowledge_bases.tenant_id IS 'Tenant that owns this knowledge base';
COMMENT ON COLUMN knowledge_bases.user_id IS 'User ID for private knowledge bases (null for tenant-level)';
COMMENT ON COLUMN knowledge_bases.name IS 'Name of the knowledge base';
COMMENT ON COLUMN knowledge_bases.description IS 'Description of the knowledge base purpose';
COMMENT ON COLUMN knowledge_bases.access_level IS 'Access control: tenant (public) or user (private)';
COMMENT ON COLUMN documents.knowledge_base_id IS 'Foreign key to knowledge_bases table';
