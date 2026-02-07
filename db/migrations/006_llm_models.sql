-- Add LLM models configuration table
-- This allows dynamic model configuration from the frontend

CREATE TABLE IF NOT EXISTS llm_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    provider VARCHAR(50) NOT NULL, -- 'openai', 'deepseek', 'local', 'mock'
    model_id VARCHAR(100) NOT NULL, -- e.g., 'gpt-4', 'deepseek-chat'
    api_base VARCHAR(500),
    api_key_encrypted TEXT, -- Encrypted API key
    config JSONB DEFAULT '{}'::jsonb, -- Additional config (temperature, max_tokens, etc.)
    enabled BOOLEAN NOT NULL DEFAULT true,
    is_default BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Indexes
CREATE INDEX idx_llm_models_provider ON llm_models(provider);
CREATE INDEX idx_llm_models_enabled ON llm_models(enabled);
CREATE INDEX idx_llm_models_tenant_id ON llm_models(tenant_id);
CREATE INDEX idx_llm_models_is_default ON llm_models(is_default);

-- Ensure only one default model per tenant
CREATE UNIQUE INDEX idx_llm_models_default_per_tenant
ON llm_models(tenant_id, is_default)
WHERE is_default = true;

-- Add model reference to messages table
ALTER TABLE messages
ADD COLUMN IF NOT EXISTS model_id UUID REFERENCES llm_models(id) ON DELETE SET NULL;

CREATE INDEX idx_messages_model_id ON messages(model_id);

-- Insert default models
INSERT INTO llm_models (name, display_name, provider, model_id, enabled, is_default, config) VALUES
('mock', 'Mock Model (Development)', 'mock', 'mock', true, true, '{"temperature": 0.7, "max_tokens": 2000}'::jsonb),
('gpt-3.5-turbo', 'GPT-3.5 Turbo', 'openai', 'gpt-3.5-turbo', false, false, '{"temperature": 0.7, "max_tokens": 2000}'::jsonb),
('gpt-4', 'GPT-4', 'openai', 'gpt-4', false, false, '{"temperature": 0.7, "max_tokens": 2000}'::jsonb),
('deepseek-chat', 'DeepSeek Chat', 'deepseek', 'deepseek-chat', false, false, '{"temperature": 0.7, "max_tokens": 2000}'::jsonb),
('deepseek-coder', 'DeepSeek Coder', 'deepseek', 'deepseek-coder', false, false, '{"temperature": 0.7, "max_tokens": 2000}'::jsonb);

-- Add comment
COMMENT ON TABLE llm_models IS 'LLM model configurations for dynamic model selection';
