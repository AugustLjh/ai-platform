-- Add model_type to llm_models for embedding/rerank support

ALTER TABLE llm_models
ADD COLUMN IF NOT EXISTS model_type VARCHAR(20) NOT NULL DEFAULT 'llm';

UPDATE llm_models
SET model_type = 'llm'
WHERE model_type IS NULL;

CREATE INDEX IF NOT EXISTS idx_llm_models_model_type ON llm_models(model_type);

COMMENT ON COLUMN llm_models.model_type IS 'Model type: llm/embedding/rerank';
