-- Remove the legacy api_key column from organizations.
-- API authentication is now handled entirely by the api_tokens table.
ALTER TABLE organizations DROP COLUMN IF EXISTS api_key;
