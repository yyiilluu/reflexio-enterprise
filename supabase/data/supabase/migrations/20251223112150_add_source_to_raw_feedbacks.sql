-- Add source column to raw_feedbacks table
ALTER TABLE raw_feedbacks ADD COLUMN IF NOT EXISTS source TEXT;
