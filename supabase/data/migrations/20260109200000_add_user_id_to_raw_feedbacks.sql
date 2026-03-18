-- Add user_id column to raw_feedbacks table
-- This allows raw feedbacks to be user-specific (like profiles)
-- The column is optional (nullable) for backward compatibility with existing data

ALTER TABLE public.raw_feedbacks ADD COLUMN IF NOT EXISTS user_id text;

-- Create index for efficient filtering by user_id
CREATE INDEX IF NOT EXISTS raw_feedbacks_user_id_idx ON public.raw_feedbacks (user_id);
