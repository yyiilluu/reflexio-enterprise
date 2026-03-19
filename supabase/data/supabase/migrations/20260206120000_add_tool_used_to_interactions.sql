-- Add tool_used column to interactions table
-- Stores which tool was used for each interaction as JSONB
-- Format: {"tool_name": "search", "tool_input": {"query": "user query"}}
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS tool_used JSONB;
