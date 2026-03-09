-- Add retrieval evaluation datasets and runs
-- Migration: 009_add_retrieval_evaluation.sql

CREATE TABLE IF NOT EXISTS retrieval_test_sets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    cases JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_test_sets_tenant_id
    ON retrieval_test_sets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_test_sets_kb_id
    ON retrieval_test_sets(knowledge_base_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_test_sets_created_at
    ON retrieval_test_sets(created_at DESC);

CREATE TRIGGER update_retrieval_test_sets_updated_at
    BEFORE UPDATE ON retrieval_test_sets
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS retrieval_test_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    test_set_id UUID REFERENCES retrieval_test_sets(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    name VARCHAR(255),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    results JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_test_runs_tenant_id
    ON retrieval_test_runs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_test_runs_kb_id
    ON retrieval_test_runs(knowledge_base_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_test_runs_test_set_id
    ON retrieval_test_runs(test_set_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_test_runs_created_at
    ON retrieval_test_runs(created_at DESC);

CREATE TRIGGER update_retrieval_test_runs_updated_at
    BEFORE UPDATE ON retrieval_test_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE retrieval_test_sets IS 'Saved retrieval evaluation datasets for a knowledge base';
COMMENT ON TABLE retrieval_test_runs IS 'Saved retrieval evaluation runs and per-case results';
