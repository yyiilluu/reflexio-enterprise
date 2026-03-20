-- Upgrade FTS query parsing from plainto_tsquery to websearch_to_tsquery
-- in all hybrid_match_* RPC functions.
--
-- websearch_to_tsquery is backward compatible with plain text AND adds:
--   - OR support: "refund OR return"
--   - Phrase matching: "exact phrase"
--   - Negation: -exclude
-- This enables the query rewriter to produce richer FTS queries.


-- ========================================================
-- 1) hybrid_match_profiles
-- ========================================================
CREATE OR REPLACE FUNCTION public.hybrid_match_profiles(
    p_query_embedding public.vector,
    p_query_text text,
    p_match_threshold double precision DEFAULT 0.3,
    p_match_count integer DEFAULT 10,
    p_current_epoch bigint DEFAULT 0,
    p_filter_user_id text DEFAULT NULL,
    p_search_mode text DEFAULT 'hybrid',
    p_rrf_k integer DEFAULT 60,
    p_filter_extractor_name text DEFAULT NULL
)
RETURNS TABLE(
    profile_id text,
    user_id text,
    content text,
    last_modified_timestamp bigint,
    generated_from_request_id text,
    profile_time_to_live text,
    expiration_timestamp bigint,
    custom_features json,
    source character varying,
    status text,
    extractor_names json,
    similarity double precision,
    fts_rank double precision,
    combined_score double precision
)
LANGUAGE plpgsql
AS $function$
DECLARE
    tsquery_val tsquery;
BEGIN
    tsquery_val := websearch_to_tsquery('english', p_query_text);

    RETURN QUERY
    WITH
    vector_results AS (
        SELECT
            p.profile_id,
            p.user_id,
            p.content,
            p.last_modified_timestamp,
            p.generated_from_request_id,
            p.profile_time_to_live,
            p.expiration_timestamp,
            p.custom_features,
            p.source,
            p.status,
            p.extractor_names,
            1 - (p.embedding <=> p_query_embedding) as vec_similarity,
            ROW_NUMBER() OVER (ORDER BY p.embedding <=> p_query_embedding) as vec_rank
        FROM profiles p
        WHERE p.expiration_timestamp >= p_current_epoch
          AND (p_search_mode = 'fts' OR 1 - (p.embedding <=> p_query_embedding) > p_match_threshold)
          AND (p_filter_user_id IS NULL OR p.user_id = p_filter_user_id)
          AND (p_filter_extractor_name IS NULL OR p.extractor_names::jsonb @> to_jsonb(p_filter_extractor_name))
          AND p.status IS NULL
        ORDER BY p.embedding <=> p_query_embedding
        LIMIT CASE WHEN p_search_mode = 'fts' THEN 0 ELSE p_match_count * 3 END
    ),
    fts_results AS (
        SELECT
            p.profile_id,
            p.user_id,
            p.content,
            p.last_modified_timestamp,
            p.generated_from_request_id,
            p.profile_time_to_live,
            p.expiration_timestamp,
            p.custom_features,
            p.source,
            p.status,
            p.extractor_names,
            ts_rank(p.content_fts, tsquery_val)::double precision as fts_score,
            ROW_NUMBER() OVER (ORDER BY ts_rank(p.content_fts, tsquery_val) DESC) as fts_rank
        FROM profiles p
        WHERE p.expiration_timestamp >= p_current_epoch
          AND (p_search_mode = 'vector' OR p.content_fts @@ tsquery_val)
          AND (p_filter_user_id IS NULL OR p.user_id = p_filter_user_id)
          AND (p_filter_extractor_name IS NULL OR p.extractor_names::jsonb @> to_jsonb(p_filter_extractor_name))
          AND p.status IS NULL
        ORDER BY ts_rank(p.content_fts, tsquery_val) DESC
        LIMIT CASE WHEN p_search_mode = 'vector' THEN 0 ELSE p_match_count * 3 END
    ),
    combined AS (
        SELECT
            COALESCE(v.profile_id, f.profile_id) as profile_id,
            COALESCE(v.user_id, f.user_id) as user_id,
            COALESCE(v.content, f.content) as content,
            COALESCE(v.last_modified_timestamp, f.last_modified_timestamp) as last_modified_timestamp,
            COALESCE(v.generated_from_request_id, f.generated_from_request_id) as generated_from_request_id,
            COALESCE(v.profile_time_to_live, f.profile_time_to_live) as profile_time_to_live,
            COALESCE(v.expiration_timestamp, f.expiration_timestamp) as expiration_timestamp,
            COALESCE(v.custom_features, f.custom_features) as custom_features,
            COALESCE(v.source, f.source) as source,
            COALESCE(v.status, f.status) as status,
            COALESCE(v.extractor_names, f.extractor_names) as extractor_names,
            v.vec_similarity as similarity,
            f.fts_score as fts_rank,
            CASE
                WHEN p_search_mode = 'vector' THEN COALESCE(v.vec_similarity, 0)
                WHEN p_search_mode = 'fts' THEN COALESCE(f.fts_score, 0)
                ELSE
                    COALESCE(1.0 / (p_rrf_k + v.vec_rank), 0) +
                    COALESCE(1.0 / (p_rrf_k + f.fts_rank), 0)
            END as combined_score
        FROM vector_results v
        FULL OUTER JOIN fts_results f ON v.profile_id = f.profile_id
    )
    SELECT
        c.profile_id,
        c.user_id,
        c.content,
        c.last_modified_timestamp,
        c.generated_from_request_id,
        c.profile_time_to_live,
        c.expiration_timestamp,
        c.custom_features,
        c.source,
        c.status,
        c.extractor_names,
        c.similarity,
        c.fts_rank,
        c.combined_score
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT p_match_count;
END;
$function$;


-- ========================================================
-- 2) hybrid_match_interactions
-- ========================================================
CREATE OR REPLACE FUNCTION public.hybrid_match_interactions(
    p_query_embedding public.vector,
    p_query_text text,
    p_match_threshold double precision DEFAULT 0.1,
    p_match_count integer DEFAULT 10,
    p_search_mode text DEFAULT 'hybrid',
    p_rrf_k integer DEFAULT 60
)
RETURNS TABLE(
    interaction_id bigint,
    user_id text,
    content text,
    request_id text,
    created_at timestamp with time zone,
    user_action text,
    user_action_description text,
    interacted_image_url text,
    similarity double precision,
    fts_rank double precision,
    combined_score double precision
)
LANGUAGE plpgsql
AS $function$
DECLARE
    tsquery_val tsquery;
BEGIN
    tsquery_val := websearch_to_tsquery('english', p_query_text);

    RETURN QUERY
    WITH
    vector_results AS (
        SELECT
            i.interaction_id,
            i.user_id,
            i.content,
            i.request_id,
            i.created_at,
            i.user_action,
            i.user_action_description,
            i.interacted_image_url,
            1 - (i.embedding <=> p_query_embedding) as vec_similarity,
            ROW_NUMBER() OVER (ORDER BY i.embedding <=> p_query_embedding) as vec_rank
        FROM interactions i
        WHERE (p_search_mode = 'fts' OR 1 - (i.embedding <=> p_query_embedding) > p_match_threshold)
        ORDER BY i.embedding <=> p_query_embedding
        LIMIT CASE WHEN p_search_mode = 'fts' THEN 0 ELSE p_match_count * 3 END
    ),
    fts_results AS (
        SELECT
            i.interaction_id,
            i.user_id,
            i.content,
            i.request_id,
            i.created_at,
            i.user_action,
            i.user_action_description,
            i.interacted_image_url,
            ts_rank(i.content_fts, tsquery_val)::double precision as fts_score,
            ROW_NUMBER() OVER (ORDER BY ts_rank(i.content_fts, tsquery_val) DESC) as fts_rank
        FROM interactions i
        WHERE (p_search_mode = 'vector' OR i.content_fts @@ tsquery_val)
        ORDER BY ts_rank(i.content_fts, tsquery_val) DESC
        LIMIT CASE WHEN p_search_mode = 'vector' THEN 0 ELSE p_match_count * 3 END
    ),
    combined AS (
        SELECT
            COALESCE(v.interaction_id, f.interaction_id) as interaction_id,
            COALESCE(v.user_id, f.user_id) as user_id,
            COALESCE(v.content, f.content) as content,
            COALESCE(v.request_id, f.request_id) as request_id,
            COALESCE(v.created_at, f.created_at) as created_at,
            COALESCE(v.user_action, f.user_action) as user_action,
            COALESCE(v.user_action_description, f.user_action_description) as user_action_description,
            COALESCE(v.interacted_image_url, f.interacted_image_url) as interacted_image_url,
            v.vec_similarity as similarity,
            f.fts_score as fts_rank,
            CASE
                WHEN p_search_mode = 'vector' THEN COALESCE(v.vec_similarity, 0)
                WHEN p_search_mode = 'fts' THEN COALESCE(f.fts_score, 0)
                ELSE
                    COALESCE(1.0 / (p_rrf_k + v.vec_rank), 0) +
                    COALESCE(1.0 / (p_rrf_k + f.fts_rank), 0)
            END as combined_score
        FROM vector_results v
        FULL OUTER JOIN fts_results f ON v.interaction_id = f.interaction_id
    )
    SELECT
        c.interaction_id,
        c.user_id,
        c.content,
        c.request_id,
        c.created_at,
        c.user_action,
        c.user_action_description,
        c.interacted_image_url,
        c.similarity,
        c.fts_rank,
        c.combined_score
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT p_match_count;
END;
$function$;


-- ========================================================
-- 3) hybrid_match_feedbacks
-- ========================================================
-- Drop the existing function because the return type (OUT parameters) changed:
-- added do_action, do_not_action, when_condition, blocking_issue, status columns.
-- PostgreSQL does not allow CREATE OR REPLACE to change return types.
DROP FUNCTION IF EXISTS public.hybrid_match_feedbacks(
    public.vector, text, double precision, integer, text, integer
);

CREATE OR REPLACE FUNCTION public.hybrid_match_feedbacks(
    p_query_embedding public.vector,
    p_query_text text,
    p_match_threshold double precision DEFAULT 0.7,
    p_match_count integer DEFAULT 10,
    p_search_mode text DEFAULT 'hybrid',
    p_rrf_k integer DEFAULT 60
)
RETURNS TABLE(
    feedback_id bigint,
    feedback_name text,
    feedback_content text,
    feedback_status text,
    agent_version text,
    feedback_metadata text,
    created_at timestamp with time zone,
    do_action text,
    do_not_action text,
    when_condition text,
    blocking_issue jsonb,
    status text,
    similarity double precision,
    fts_rank double precision,
    combined_score double precision,
    embedding public.vector
)
LANGUAGE plpgsql
AS $function$
DECLARE
    tsquery_val tsquery;
BEGIN
    tsquery_val := websearch_to_tsquery('english', p_query_text);

    RETURN QUERY
    WITH
    vector_results AS (
        SELECT
            f.feedback_id,
            f.feedback_name,
            f.feedback_content,
            f.feedback_status,
            f.agent_version,
            f.feedback_metadata,
            f.created_at,
            f.do_action,
            f.do_not_action,
            f.when_condition,
            f.blocking_issue,
            f.status,
            f.embedding,
            1 - (f.embedding <=> p_query_embedding) as vec_similarity,
            ROW_NUMBER() OVER (ORDER BY f.embedding <=> p_query_embedding) as vec_rank
        FROM feedbacks f
        WHERE (p_search_mode = 'fts' OR 1 - (f.embedding <=> p_query_embedding) > p_match_threshold)
          AND f.status IS NULL
        ORDER BY f.embedding <=> p_query_embedding
        LIMIT CASE WHEN p_search_mode = 'fts' THEN 0 ELSE p_match_count * 3 END
    ),
    fts_results AS (
        SELECT
            f.feedback_id,
            f.feedback_name,
            f.feedback_content,
            f.feedback_status,
            f.agent_version,
            f.feedback_metadata,
            f.created_at,
            f.do_action,
            f.do_not_action,
            f.when_condition,
            f.blocking_issue,
            f.status,
            f.embedding,
            ts_rank(f.feedback_content_fts, tsquery_val)::double precision as fts_score,
            ROW_NUMBER() OVER (ORDER BY ts_rank(f.feedback_content_fts, tsquery_val) DESC) as fts_rank
        FROM feedbacks f
        WHERE (p_search_mode = 'vector' OR f.feedback_content_fts @@ tsquery_val)
          AND f.status IS NULL
        ORDER BY ts_rank(f.feedback_content_fts, tsquery_val) DESC
        LIMIT CASE WHEN p_search_mode = 'vector' THEN 0 ELSE p_match_count * 3 END
    ),
    combined AS (
        SELECT
            COALESCE(v.feedback_id, f.feedback_id) as feedback_id,
            COALESCE(v.feedback_name, f.feedback_name) as feedback_name,
            COALESCE(v.feedback_content, f.feedback_content) as feedback_content,
            COALESCE(v.feedback_status, f.feedback_status) as feedback_status,
            COALESCE(v.agent_version, f.agent_version) as agent_version,
            COALESCE(v.feedback_metadata, f.feedback_metadata) as feedback_metadata,
            COALESCE(v.created_at, f.created_at) as created_at,
            COALESCE(v.do_action, f.do_action) as do_action,
            COALESCE(v.do_not_action, f.do_not_action) as do_not_action,
            COALESCE(v.when_condition, f.when_condition) as when_condition,
            COALESCE(v.blocking_issue, f.blocking_issue) as blocking_issue,
            COALESCE(v.status, f.status) as status,
            COALESCE(v.embedding, f.embedding) as embedding,
            v.vec_similarity as similarity,
            f.fts_score as fts_rank,
            CASE
                WHEN p_search_mode = 'vector' THEN COALESCE(v.vec_similarity, 0)
                WHEN p_search_mode = 'fts' THEN COALESCE(f.fts_score, 0)
                ELSE
                    COALESCE(1.0 / (p_rrf_k + v.vec_rank), 0) +
                    COALESCE(1.0 / (p_rrf_k + f.fts_rank), 0)
            END as combined_score
        FROM vector_results v
        FULL OUTER JOIN fts_results f ON v.feedback_id = f.feedback_id
    )
    SELECT
        c.feedback_id,
        c.feedback_name,
        c.feedback_content,
        c.feedback_status,
        c.agent_version,
        c.feedback_metadata,
        c.created_at,
        c.do_action,
        c.do_not_action,
        c.when_condition,
        c.blocking_issue,
        c.status,
        c.similarity,
        c.fts_rank,
        c.combined_score,
        c.embedding
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT p_match_count;
END;
$function$;


-- ========================================================
-- 4) hybrid_match_raw_feedbacks
-- ========================================================
-- Drop the old 6-param overload (without p_filter_user_id) so CREATE OR REPLACE
-- can install the new 7-param version. Without this DROP, PostgreSQL treats the
-- different parameter list as a separate overload and keeps the old one.
DROP FUNCTION IF EXISTS public.hybrid_match_raw_feedbacks(
    public.vector, text, double precision, integer, text, integer
);

CREATE OR REPLACE FUNCTION public.hybrid_match_raw_feedbacks(
    p_query_embedding public.vector,
    p_query_text text,
    p_match_threshold double precision DEFAULT 0.7,
    p_match_count integer DEFAULT 10,
    p_filter_user_id text DEFAULT NULL,
    p_search_mode text DEFAULT 'hybrid',
    p_rrf_k integer DEFAULT 60
)
RETURNS TABLE(
    raw_feedback_id bigint,
    user_id text,
    feedback_name text,
    request_id text,
    agent_version text,
    feedback_content text,
    do_action text,
    do_not_action text,
    when_condition text,
    blocking_issue jsonb,
    source text,
    status text,
    created_at timestamp with time zone,
    similarity double precision,
    fts_rank double precision,
    combined_score double precision,
    embedding public.vector
)
LANGUAGE plpgsql
AS $function$
DECLARE
    tsquery_val tsquery;
BEGIN
    tsquery_val := websearch_to_tsquery('english', p_query_text);

    RETURN QUERY
    WITH
    vector_results AS (
        SELECT
            rf.raw_feedback_id,
            rf.user_id,
            rf.feedback_name,
            rf.request_id,
            rf.agent_version,
            rf.feedback_content,
            rf.do_action,
            rf.do_not_action,
            rf.when_condition,
            rf.blocking_issue,
            rf.source,
            rf.status,
            rf.created_at,
            rf.embedding,
            1 - (rf.embedding <=> p_query_embedding) as vec_similarity,
            ROW_NUMBER() OVER (ORDER BY rf.embedding <=> p_query_embedding) as vec_rank
        FROM raw_feedbacks rf
        WHERE (p_search_mode = 'fts' OR 1 - (rf.embedding <=> p_query_embedding) > p_match_threshold)
          AND rf.status IS NULL
          AND (p_filter_user_id IS NULL OR rf.user_id = p_filter_user_id)
        ORDER BY rf.embedding <=> p_query_embedding
        LIMIT CASE WHEN p_search_mode = 'fts' THEN 0 ELSE p_match_count * 3 END
    ),
    fts_results AS (
        SELECT
            rf.raw_feedback_id,
            rf.user_id,
            rf.feedback_name,
            rf.request_id,
            rf.agent_version,
            rf.feedback_content,
            rf.do_action,
            rf.do_not_action,
            rf.when_condition,
            rf.blocking_issue,
            rf.source,
            rf.status,
            rf.created_at,
            rf.embedding,
            ts_rank(rf.feedback_content_fts, tsquery_val)::double precision as fts_score,
            ROW_NUMBER() OVER (ORDER BY ts_rank(rf.feedback_content_fts, tsquery_val) DESC) as fts_rank
        FROM raw_feedbacks rf
        WHERE (p_search_mode = 'vector' OR rf.feedback_content_fts @@ tsquery_val)
          AND rf.status IS NULL
          AND (p_filter_user_id IS NULL OR rf.user_id = p_filter_user_id)
        ORDER BY ts_rank(rf.feedback_content_fts, tsquery_val) DESC
        LIMIT CASE WHEN p_search_mode = 'vector' THEN 0 ELSE p_match_count * 3 END
    ),
    combined AS (
        SELECT
            COALESCE(v.raw_feedback_id, f.raw_feedback_id) as raw_feedback_id,
            COALESCE(v.user_id, f.user_id) as user_id,
            COALESCE(v.feedback_name, f.feedback_name) as feedback_name,
            COALESCE(v.request_id, f.request_id) as request_id,
            COALESCE(v.agent_version, f.agent_version) as agent_version,
            COALESCE(v.feedback_content, f.feedback_content) as feedback_content,
            COALESCE(v.do_action, f.do_action) as do_action,
            COALESCE(v.do_not_action, f.do_not_action) as do_not_action,
            COALESCE(v.when_condition, f.when_condition) as when_condition,
            COALESCE(v.blocking_issue, f.blocking_issue) as blocking_issue,
            COALESCE(v.source, f.source) as source,
            COALESCE(v.status, f.status) as status,
            COALESCE(v.created_at, f.created_at) as created_at,
            COALESCE(v.embedding, f.embedding) as embedding,
            v.vec_similarity as similarity,
            f.fts_score as fts_rank,
            CASE
                WHEN p_search_mode = 'vector' THEN COALESCE(v.vec_similarity, 0)
                WHEN p_search_mode = 'fts' THEN COALESCE(f.fts_score, 0)
                ELSE
                    COALESCE(1.0 / (p_rrf_k + v.vec_rank), 0) +
                    COALESCE(1.0 / (p_rrf_k + f.fts_rank), 0)
            END as combined_score
        FROM vector_results v
        FULL OUTER JOIN fts_results f ON v.raw_feedback_id = f.raw_feedback_id
    )
    SELECT
        c.raw_feedback_id,
        c.user_id,
        c.feedback_name,
        c.request_id,
        c.agent_version,
        c.feedback_content,
        c.do_action,
        c.do_not_action,
        c.when_condition,
        c.blocking_issue,
        c.source,
        c.status,
        c.created_at,
        c.similarity,
        c.fts_rank,
        c.combined_score,
        c.embedding
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT p_match_count;
END;
$function$;


-- ========================================================
-- 5) hybrid_match_skills
-- ========================================================
CREATE OR REPLACE FUNCTION public.hybrid_match_skills(
    p_query_embedding public.vector,
    p_query_text text,
    p_match_threshold double precision DEFAULT 0.3,
    p_match_count integer DEFAULT 10,
    p_org_id text DEFAULT NULL,
    p_search_mode text DEFAULT 'hybrid',
    p_rrf_k integer DEFAULT 60
)
RETURNS TABLE(
    skill_id bigint,
    org_id text,
    skill_name text,
    description text,
    version text,
    agent_version text,
    feedback_name text,
    instructions text,
    allowed_tools jsonb,
    blocking_issues jsonb,
    raw_feedback_ids jsonb,
    skill_status text,
    embedding public.vector,
    created_at timestamptz,
    updated_at timestamptz,
    similarity double precision,
    fts_rank double precision,
    combined_score double precision
)
LANGUAGE plpgsql
AS $function$
DECLARE
    tsquery_val tsquery;
BEGIN
    tsquery_val := websearch_to_tsquery('english', p_query_text);

    RETURN QUERY
    WITH
    vector_results AS (
        SELECT
            s.skill_id,
            s.org_id,
            s.skill_name,
            s.description,
            s.version,
            s.agent_version,
            s.feedback_name,
            s.instructions,
            s.allowed_tools,
            s.blocking_issues,
            s.raw_feedback_ids,
            s.skill_status,
            s.embedding,
            s.created_at,
            s.updated_at,
            1 - (s.embedding <=> p_query_embedding) as vec_similarity,
            ROW_NUMBER() OVER (ORDER BY s.embedding <=> p_query_embedding) as vec_rank
        FROM public.skills s
        WHERE (p_search_mode = 'fts' OR 1 - (s.embedding <=> p_query_embedding) > p_match_threshold)
          AND (p_org_id IS NULL OR s.org_id = p_org_id)
        ORDER BY s.embedding <=> p_query_embedding
        LIMIT CASE WHEN p_search_mode = 'fts' THEN 0 ELSE p_match_count * 3 END
    ),
    fts_results AS (
        SELECT
            s.skill_id,
            s.org_id,
            s.skill_name,
            s.description,
            s.version,
            s.agent_version,
            s.feedback_name,
            s.instructions,
            s.allowed_tools,
            s.blocking_issues,
            s.raw_feedback_ids,
            s.skill_status,
            s.embedding,
            s.created_at,
            s.updated_at,
            ts_rank(s.content_fts, tsquery_val)::double precision as fts_score,
            ROW_NUMBER() OVER (ORDER BY ts_rank(s.content_fts, tsquery_val) DESC) as fts_rank
        FROM public.skills s
        WHERE (p_search_mode = 'vector' OR s.content_fts @@ tsquery_val)
          AND (p_org_id IS NULL OR s.org_id = p_org_id)
        ORDER BY ts_rank(s.content_fts, tsquery_val) DESC
        LIMIT CASE WHEN p_search_mode = 'vector' THEN 0 ELSE p_match_count * 3 END
    ),
    combined AS (
        SELECT
            COALESCE(v.skill_id, f.skill_id) as skill_id,
            COALESCE(v.org_id, f.org_id) as org_id,
            COALESCE(v.skill_name, f.skill_name) as skill_name,
            COALESCE(v.description, f.description) as description,
            COALESCE(v.version, f.version) as version,
            COALESCE(v.agent_version, f.agent_version) as agent_version,
            COALESCE(v.feedback_name, f.feedback_name) as feedback_name,
            COALESCE(v.instructions, f.instructions) as instructions,
            COALESCE(v.allowed_tools, f.allowed_tools) as allowed_tools,
            COALESCE(v.blocking_issues, f.blocking_issues) as blocking_issues,
            COALESCE(v.raw_feedback_ids, f.raw_feedback_ids) as raw_feedback_ids,
            COALESCE(v.skill_status, f.skill_status) as skill_status,
            COALESCE(v.embedding, f.embedding) as embedding,
            COALESCE(v.created_at, f.created_at) as created_at,
            COALESCE(v.updated_at, f.updated_at) as updated_at,
            v.vec_similarity as similarity,
            f.fts_score as fts_rank,
            CASE
                WHEN p_search_mode = 'vector' THEN COALESCE(v.vec_similarity, 0)
                WHEN p_search_mode = 'fts' THEN COALESCE(f.fts_score, 0)
                ELSE
                    COALESCE(1.0 / (p_rrf_k + v.vec_rank), 0) +
                    COALESCE(1.0 / (p_rrf_k + f.fts_rank), 0)
            END as combined_score
        FROM vector_results v
        FULL OUTER JOIN fts_results f ON v.skill_id = f.skill_id
    )
    SELECT
        c.skill_id,
        c.org_id,
        c.skill_name,
        c.description,
        c.version,
        c.agent_version,
        c.feedback_name,
        c.instructions,
        c.allowed_tools,
        c.blocking_issues,
        c.raw_feedback_ids,
        c.skill_status,
        c.embedding,
        c.created_at,
        c.updated_at,
        c.similarity,
        c.fts_rank,
        c.combined_score
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT p_match_count;
END;
$function$;
