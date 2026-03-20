-- Add structured feedback fields to raw_feedbacks and feedbacks tables
-- These fields support the structured feedback format: do_action, do_not_action, when_condition

-- Add columns to raw_feedbacks table
ALTER TABLE raw_feedbacks
ADD COLUMN IF NOT EXISTS do_action TEXT,
ADD COLUMN IF NOT EXISTS do_not_action TEXT,
ADD COLUMN IF NOT EXISTS when_condition TEXT;

-- Add columns to feedbacks table
ALTER TABLE feedbacks
ADD COLUMN IF NOT EXISTS do_action TEXT,
ADD COLUMN IF NOT EXISTS do_not_action TEXT,
ADD COLUMN IF NOT EXISTS when_condition TEXT;

-- Add comment explaining the new columns
COMMENT ON COLUMN raw_feedbacks.do_action IS 'The preferred behavior the agent should adopt (structured feedback v1.2.0+)';
COMMENT ON COLUMN raw_feedbacks.do_not_action IS 'The mistaken behavior the agent should avoid (structured feedback v1.2.0+)';
COMMENT ON COLUMN raw_feedbacks.when_condition IS 'The condition/context when this rule applies (structured feedback v1.2.0+)';

COMMENT ON COLUMN feedbacks.do_action IS 'The preferred behavior the agent should adopt (structured feedback v1.2.0+)';
COMMENT ON COLUMN feedbacks.do_not_action IS 'The mistaken behavior the agent should avoid (structured feedback v1.2.0+)';
COMMENT ON COLUMN feedbacks.when_condition IS 'The condition/context when this rule applies (structured feedback v1.2.0+)';
