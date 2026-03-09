-- Add quota tracking period columns
-- Migration: 008_add_quota_periods.sql

ALTER TABLE quotas
ADD COLUMN IF NOT EXISTS period_start TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS period_end TIMESTAMP WITH TIME ZONE DEFAULT NOW() + INTERVAL '1 month';

-- Backfill existing rows using legacy reset_period/last_reset_at if present
UPDATE quotas
SET period_start = COALESCE(period_start, last_reset_at, created_at, NOW()),
    period_end = COALESCE(
        period_end,
        CASE
            WHEN reset_period = 'daily' THEN COALESCE(last_reset_at, created_at, NOW()) + INTERVAL '1 day'
            WHEN reset_period = 'yearly' THEN COALESCE(last_reset_at, created_at, NOW()) + INTERVAL '1 year'
            ELSE COALESCE(last_reset_at, created_at, NOW()) + INTERVAL '1 month'
        END
    )
WHERE period_start IS NULL OR period_end IS NULL;

-- Optional helper index for querying upcoming quota windows
CREATE INDEX IF NOT EXISTS idx_quotas_period_end ON quotas(period_end);

COMMENT ON COLUMN quotas.period_start IS 'Quota tracking period start time';
COMMENT ON COLUMN quotas.period_end IS 'Quota tracking period end time';
