-- Add blocking_issue JSONB column to raw_feedbacks and feedbacks tables
-- This field stores the root cause when agent could not complete an action (kind + details)

ALTER TABLE raw_feedbacks ADD COLUMN IF NOT EXISTS blocking_issue JSONB;
ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS blocking_issue JSONB;

COMMENT ON COLUMN raw_feedbacks.blocking_issue IS 'Root cause when agent could not complete action (kind + details)';
COMMENT ON COLUMN feedbacks.blocking_issue IS 'Root cause when agent could not complete action (kind + details)';
