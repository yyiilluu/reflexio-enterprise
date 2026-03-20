-- Add evaluation_name column if it doesn't already exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'agent_success_evaluation_result'
        AND column_name = 'evaluation_name'
    ) THEN
        ALTER TABLE "public"."agent_success_evaluation_result" ADD COLUMN "evaluation_name" text;
    END IF;
END $$;
