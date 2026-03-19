ALTER TABLE organizations ADD COLUMN auth_provider VARCHAR(20) NOT NULL DEFAULT 'email';
