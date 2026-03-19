-- Fix query timeout in get_request_groups (error 57014).
-- Adds three missing indexes for the PostgREST embedded-resource query.

CREATE INDEX IF NOT EXISTS idx_requests_created_at
    ON public.requests (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_requests_user_id_created_at
    ON public.requests (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_interactions_request_id
    ON public.interactions (request_id);
