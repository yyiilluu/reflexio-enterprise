-- Migration: Add start_time and end_time filters to get_last_k_interactions
-- This enables filtering interactions by time range when retrieving data

-- Drop existing function to update signature (adding p_start_time and p_end_time parameters)
DROP FUNCTION IF EXISTS public.get_last_k_interactions(text, int, text);

CREATE OR REPLACE FUNCTION public.get_last_k_interactions(
    p_user_id text DEFAULT NULL,  -- NULL means get all users
    p_limit int DEFAULT 100,
    p_source text DEFAULT NULL,
    p_start_time bigint DEFAULT NULL,  -- Unix timestamp: only return interactions created at or after this time
    p_end_time bigint DEFAULT NULL     -- Unix timestamp: only return interactions created at or before this time
)
RETURNS TABLE(
    request_id text,
    request_user_id text,
    request_created_at timestamp with time zone,
    request_source text,
    request_agent_version text,
    request_group text,
    interaction_id bigint,
    interaction_user_id text,
    interaction_content text,
    interaction_request_id text,
    interaction_created_at timestamp with time zone,
    interaction_role text,
    interaction_user_action text,
    interaction_user_action_description text,
    interaction_interacted_image_url text,
    interaction_shadow_content text
)
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    WITH last_k_interactions AS (
        SELECT i.*
        FROM interactions i
        INNER JOIN requests r ON i.request_id = r.request_id
        WHERE (p_user_id IS NULL OR i.user_id = p_user_id)
          AND (p_source IS NULL OR r.source = p_source)
          AND (p_start_time IS NULL OR i.created_at >= to_timestamp(p_start_time))
          AND (p_end_time IS NULL OR i.created_at <= to_timestamp(p_end_time))
        ORDER BY i.interaction_id DESC
        LIMIT p_limit
    )
    SELECT
        r.request_id,
        r.user_id as request_user_id,
        r.created_at as request_created_at,
        r.source as request_source,
        r.agent_version as request_agent_version,
        r.request_group,
        lki.interaction_id,
        lki.user_id as interaction_user_id,
        lki.content as interaction_content,
        lki.request_id as interaction_request_id,
        lki.created_at as interaction_created_at,
        lki.role as interaction_role,
        lki.user_action as interaction_user_action,
        lki.user_action_description as interaction_user_action_description,
        lki.interacted_image_url as interaction_interacted_image_url,
        lki.shadow_content as interaction_shadow_content
    FROM last_k_interactions lki
    INNER JOIN requests r ON lki.request_id = r.request_id
    ORDER BY lki.interaction_id DESC;
END;
$function$;
