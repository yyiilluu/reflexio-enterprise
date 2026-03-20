-- Add composite index on requests(request_group, created_at DESC) to speed up
-- filtered + ordered queries on the interactions page.
CREATE INDEX IF NOT EXISTS requests_request_group_created_at_idx
    ON requests (request_group, created_at DESC);
