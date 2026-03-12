-- Remove embedding column from hybrid search RPC return types.
-- Embeddings are 512-dim float vectors (~2KB each as JSON) and callers never use them from search results.
-- The functions still READ embedding columns internally for similarity calculations.

-- ========================================================
-- 1) hybrid_match_feedbacks — drop and recreate without embedding in RETURNS TABLE
-- ========================================================
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
        c.combined_score
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT p_match_count;
END;
$function$;


-- ========================================================
-- 2) hybrid_match_raw_feedbacks — drop and recreate without embedding in RETURNS TABLE
-- ========================================================
DROP FUNCTION IF EXISTS public.hybrid_match_raw_feedbacks(
    public.vector, text, double precision, integer, text, text, integer
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
        c.combined_score
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT p_match_count;
END;
$function$;
