-- Rename request_group to session_id across all tables and update
-- dependent indexes, constraints, and RPC functions.

-- ============================================================
-- 1. requests table
-- ============================================================
ALTER TABLE requests RENAME COLUMN request_group TO session_id;

DROP INDEX IF EXISTS requests_request_group_created_at_idx;
CREATE INDEX requests_session_id_created_at_idx
    ON requests (session_id, created_at DESC);

-- ============================================================
-- 2. agent_success_evaluation_result table
-- ============================================================
ALTER TABLE agent_success_evaluation_result DROP CONSTRAINT IF EXISTS agent_success_evaluation_result_request_id_key;

ALTER TABLE agent_success_evaluation_result RENAME COLUMN request_id TO session_id;

CREATE UNIQUE INDEX agent_success_evaluation_result_session_id_eval_name_key
    ON agent_success_evaluation_result (session_id, evaluation_name);
ALTER TABLE agent_success_evaluation_result
    ADD CONSTRAINT agent_success_evaluation_result_session_id_eval_name_key
    UNIQUE USING INDEX agent_success_evaluation_result_session_id_eval_name_key;

-- ============================================================
-- 3. Recreate get_last_k_interactions with session_id
-- ============================================================
DROP FUNCTION IF EXISTS public.get_last_k_interactions(text, int, text[], bigint, bigint, text);

CREATE OR REPLACE FUNCTION public.get_last_k_interactions(
    p_user_id text DEFAULT NULL,
    p_limit int DEFAULT 100,
    p_sources text[] DEFAULT NULL,
    p_start_time bigint DEFAULT NULL,
    p_end_time bigint DEFAULT NULL,
    p_agent_version text DEFAULT NULL
)
RETURNS TABLE(
    request_id text,
    request_user_id text,
    request_created_at timestamp with time zone,
    request_source text,
    request_agent_version text,
    session_id text,
    interaction_id bigint,
    interaction_user_id text,
    interaction_content text,
    interaction_request_id text,
    interaction_created_at timestamp with time zone,
    interaction_role text,
    interaction_user_action text,
    interaction_user_action_description text,
    interaction_interacted_image_url text,
    interaction_shadow_content text,
    interaction_tools_used jsonb
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
          AND (p_sources IS NULL OR r.source = ANY(p_sources))
          AND (p_start_time IS NULL OR i.created_at >= to_timestamp(p_start_time))
          AND (p_end_time IS NULL OR i.created_at <= to_timestamp(p_end_time))
          AND (p_agent_version IS NULL OR r.agent_version = p_agent_version)
        ORDER BY i.interaction_id DESC
        LIMIT p_limit
    )
    SELECT
        r.request_id,
        r.user_id as request_user_id,
        r.created_at as request_created_at,
        r.source as request_source,
        r.agent_version as request_agent_version,
        r.session_id,
        lki.interaction_id,
        lki.user_id as interaction_user_id,
        lki.content as interaction_content,
        lki.request_id as interaction_request_id,
        lki.created_at as interaction_created_at,
        lki.role as interaction_role,
        lki.user_action as interaction_user_action,
        lki.user_action_description as interaction_user_action_description,
        lki.interacted_image_url as interaction_interacted_image_url,
        lki.shadow_content as interaction_shadow_content,
        lki.tools_used as interaction_tools_used
    FROM last_k_interactions lki
    INNER JOIN requests r ON lki.request_id = r.request_id
    ORDER BY lki.interaction_id DESC;
END;
$function$;

-- ============================================================
-- 4. Recreate get_new_request_interaction_groups with session_id
-- ============================================================
DROP FUNCTION IF EXISTS public.get_new_request_interaction_groups(text, timestamp with time zone, bigint[], text[]);

CREATE OR REPLACE FUNCTION public.get_new_request_interaction_groups(
    p_user_id text DEFAULT NULL,
    p_last_processed_timestamp timestamp with time zone DEFAULT NULL,
    p_excluded_interaction_ids bigint[] DEFAULT ARRAY[]::bigint[],
    p_sources text[] DEFAULT NULL
)
RETURNS TABLE(
    request_id text,
    request_user_id text,
    request_created_at timestamp with time zone,
    request_source text,
    request_agent_version text,
    session_id text,
    interaction_id bigint,
    interaction_user_id text,
    interaction_content text,
    interaction_request_id text,
    interaction_created_at timestamp with time zone,
    interaction_role text,
    interaction_user_action text,
    interaction_user_action_description text,
    interaction_interacted_image_url text,
    interaction_shadow_content text,
    interaction_tools_used jsonb
)
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        r.request_id,
        r.user_id as request_user_id,
        r.created_at as request_created_at,
        r.source as request_source,
        r.agent_version as request_agent_version,
        r.session_id,
        i.interaction_id,
        i.user_id as interaction_user_id,
        i.content as interaction_content,
        i.request_id as interaction_request_id,
        i.created_at as interaction_created_at,
        i.role as interaction_role,
        i.user_action as interaction_user_action,
        i.user_action_description as interaction_user_action_description,
        i.interacted_image_url as interaction_interacted_image_url,
        i.shadow_content as interaction_shadow_content,
        i.tools_used as interaction_tools_used
    FROM requests r
    INNER JOIN interactions i ON r.request_id = i.request_id
    WHERE (p_user_id IS NULL OR r.user_id = p_user_id)
      AND (p_user_id IS NULL OR i.user_id = p_user_id)
      AND (p_last_processed_timestamp IS NULL OR i.created_at >= p_last_processed_timestamp)
      AND NOT (i.interaction_id = ANY(p_excluded_interaction_ids))
      AND (p_sources IS NULL OR r.source = ANY(p_sources))
    ORDER BY i.interaction_id ASC;
END;
$function$;
