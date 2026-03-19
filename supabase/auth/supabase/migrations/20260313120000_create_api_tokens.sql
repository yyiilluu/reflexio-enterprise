-- Create api_tokens table for multi-token API key system
CREATE TABLE IF NOT EXISTS api_tokens (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    token VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL DEFAULT 'Default',
    created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())::INTEGER,
    last_used_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_token ON api_tokens(token);
CREATE INDEX IF NOT EXISTS idx_api_tokens_org_id ON api_tokens(org_id);

-- Migrate existing api_key values from organizations table into api_tokens.
-- Only migrate short tokens (rflx- format, <=40 chars). Skip old JWT tokens
-- which are 200+ chars and would violate the VARCHAR(40) constraint.
INSERT INTO api_tokens (org_id, token, name, created_at)
SELECT id, api_key, 'Default', created_at
FROM organizations
WHERE api_key IS NOT NULL AND api_key != '' AND length(api_key) <= 40
ON CONFLICT (token) DO NOTHING;
