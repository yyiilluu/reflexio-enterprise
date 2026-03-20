CREATE TABLE IF NOT EXISTS invitation_codes (
    id SERIAL PRIMARY KEY,
    code VARCHAR(255) UNIQUE NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    used_by_email VARCHAR(255),
    used_at INTEGER,
    created_at INTEGER NOT NULL,
    expires_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_invitation_codes_code ON invitation_codes(code);
