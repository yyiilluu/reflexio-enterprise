-- Fix FTS tsvector source columns for feedbacks and raw_feedbacks tables
-- feedbacks: should include 'when_condition' in addition to 'feedback_content'
-- raw_feedbacks: should use 'indexed_content' instead of 'feedback_content'

-- ================================================
-- Fix feedbacks: generate from when_condition + feedback_content
-- ================================================
ALTER TABLE feedbacks DROP COLUMN IF EXISTS feedback_content_fts;
ALTER TABLE feedbacks ADD COLUMN feedback_content_fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(when_condition, '') || ' ' || coalesce(feedback_content, ''))
  ) STORED;

CREATE INDEX IF NOT EXISTS idx_feedbacks_feedback_content_fts ON feedbacks USING GIN (feedback_content_fts);

-- ================================================
-- Fix raw_feedbacks: generate from indexed_content
-- ================================================
ALTER TABLE raw_feedbacks DROP COLUMN IF EXISTS feedback_content_fts;
ALTER TABLE raw_feedbacks ADD COLUMN feedback_content_fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(indexed_content, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_raw_feedbacks_feedback_content_fts ON raw_feedbacks USING GIN (feedback_content_fts);
