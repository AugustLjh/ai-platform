-- Data migration script to create default knowledge bases and link existing documents
-- Migration: 005_migrate_existing_documents.sql

-- Create a default knowledge base for each tenant that has documents
INSERT INTO knowledge_bases (tenant_id, name, description, access_level, metadata)
SELECT DISTINCT
    tenant_id,
    'Default Knowledge Base',
    'Auto-created during migration to contain existing documents',
    'tenant',
    jsonb_build_object('migrated', true, 'created_at', NOW()::text)
FROM documents
WHERE tenant_id NOT IN (SELECT tenant_id FROM knowledge_bases WHERE name = 'Default Knowledge Base')
ON CONFLICT DO NOTHING;

-- Update all documents without a knowledge_base_id to link to their tenant's default knowledge base
UPDATE documents d
SET knowledge_base_id = kb.id
FROM knowledge_bases kb
WHERE d.tenant_id = kb.tenant_id
  AND kb.name = 'Default Knowledge Base'
  AND d.knowledge_base_id IS NULL;

-- Verify migration
DO $$
DECLARE
    orphaned_count INTEGER;
    migrated_count INTEGER;
BEGIN
    -- Check for orphaned documents
    SELECT COUNT(*) INTO orphaned_count
    FROM documents
    WHERE knowledge_base_id IS NULL;

    -- Count migrated documents
    SELECT COUNT(*) INTO migrated_count
    FROM documents d
    JOIN knowledge_bases kb ON d.knowledge_base_id = kb.id
    WHERE kb.metadata->>'migrated' = 'true';

    RAISE NOTICE 'Migration complete:';
    RAISE NOTICE '  - Migrated documents: %', migrated_count;
    RAISE NOTICE '  - Orphaned documents: %', orphaned_count;

    IF orphaned_count > 0 THEN
        RAISE WARNING 'Found % orphaned documents without knowledge_base_id', orphaned_count;
    END IF;
END $$;

-- Make knowledge_base_id NOT NULL after migration is verified
ALTER TABLE documents ALTER COLUMN knowledge_base_id SET NOT NULL;
