-- Migration: Create organizations table for user authentication
-- This table stores login credentials and organization configuration.
-- It matches the SQLAlchemy model in reflexio/server/db/db_models.py

CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())::INTEGER,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    configuration_json TEXT DEFAULT '',
    api_key VARCHAR(255) DEFAULT ''
);

-- Create index on email for fast login lookups
CREATE INDEX IF NOT EXISTS idx_organizations_email ON organizations(email);

-- Enable Row Level Security (recommended for Supabase)
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

-- Policy: Allow service role full access (for backend operations)
-- Note: In production, you may want more granular policies
CREATE POLICY "Service role has full access" ON organizations
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
