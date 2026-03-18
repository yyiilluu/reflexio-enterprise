-- Add indexed_content column to raw_feedbacks table
-- This stores the extracted content used for embedding generation
-- For prompt version >= 1.1.0, this contains the "when" condition from feedback
-- The column is optional (nullable) - when null, full feedback_content is used for embedding

ALTER TABLE public.raw_feedbacks ADD COLUMN IF NOT EXISTS indexed_content text;
