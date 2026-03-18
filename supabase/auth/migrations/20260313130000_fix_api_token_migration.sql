-- Clean up any non-rflx tokens that may have been migrated from old JWT api_keys.
-- The api_tokens table is designed for short rflx- prefixed tokens only.
DELETE FROM api_tokens WHERE token NOT LIKE 'rflx-%';
