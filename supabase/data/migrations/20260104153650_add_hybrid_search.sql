-- Add hybrid search support: tsvector columns, GIN indexes, and hybrid RPC functions
-- This enables combining vector similarity search with PostgreSQL full-text search (FTS)
-- using Reciprocal Rank Fusion (RRF) for improved keyword matching

-- Increase maintenance_work_mem for GIN index creation (required for larger tables)
SET LOCAL maintenance_work_mem = '128MB';

-- ================================================
-- STEP 1: Add tsvector columns (auto-generated from text columns)
-- ================================================

-- profiles: searchable on 'content' column
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS content_fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;

-- interactions: searchable on 'content' + 'user_action_description'
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS content_fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(content, '') || ' ' || coalesce(user_action_description, ''))
  ) STORED;

-- feedbacks: searchable on 'feedback_content'
ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS feedback_content_fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(feedback_content, ''))) STORED;

-- raw_feedbacks: searchable on 'feedback_content'
ALTER TABLE raw_feedbacks ADD COLUMN IF NOT EXISTS feedback_content_fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(feedback_content, ''))) STORED;

-- ================================================
-- STEP 2: Create GIN indexes for full-text search
-- ================================================

CREATE INDEX IF NOT EXISTS idx_profiles_content_fts ON profiles USING GIN (content_fts);
CREATE INDEX IF NOT EXISTS idx_interactions_content_fts ON interactions USING GIN (content_fts);
CREATE INDEX IF NOT EXISTS idx_feedbacks_feedback_content_fts ON feedbacks USING GIN (feedback_content_fts);
CREATE INDEX IF NOT EXISTS idx_raw_feedbacks_feedback_content_fts ON raw_feedbacks USING GIN (feedback_content_fts);

-- ================================================
-- STEP 3: Create hybrid search RPC functions
-- ================================================

-- --------------------------------------------------------
-- hybrid_match_profiles: Combines vector + FTS using RRF
-- --------------------------------------------------------
CREATE OR REPLACE FUNCTION public.hybrid_match_profiles(
    p_query_embedding public.vector,
    p_query_text text,
    p_match_threshold double precision DEFAULT 0.3,
    p_match_count integer DEFAULT 10,
    p_current_epoch bigint DEFAULT 0,
    p_filter_user_id text DEFAULT NULL,
    p_search_mode text DEFAULT 'hybrid',
    p_rrf_k integer DEFAULT 60
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
    similarity double precision,
    fts_rank double precision,
    combined_score double precision
)
LANGUAGE plpgsql
AS $function$
DECLARE
    tsquery_val tsquery;
BEGIN
    -- Convert text query to tsquery for FTS
    tsquery_val := plainto_tsquery('english', p_query_text);

    RETURN QUERY
    WITH
    -- Vector search results with ranking
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
            1 - (p.embedding <=> p_query_embedding) as vec_similarity,
            ROW_NUMBER() OVER (ORDER BY p.embedding <=> p_query_embedding) as vec_rank
        FROM profiles p
        WHERE p.expiration_timestamp >= p_current_epoch
          AND (p_search_mode = 'fts' OR 1 - (p.embedding <=> p_query_embedding) > p_match_threshold)
          AND (p_filter_user_id IS NULL OR p.user_id = p_filter_user_id)
          AND p.status IS NULL
        ORDER BY p.embedding <=> p_query_embedding
        LIMIT CASE WHEN p_search_mode = 'fts' THEN 0 ELSE p_match_count * 3 END
    ),
    -- FTS results with ranking
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
            ts_rank(p.content_fts, tsquery_val)::double precision as fts_score,
            ROW_NUMBER() OVER (ORDER BY ts_rank(p.content_fts, tsquery_val) DESC) as fts_rank
        FROM profiles p
        WHERE p.expiration_timestamp >= p_current_epoch
          AND (p_search_mode = 'vector' OR p.content_fts @@ tsquery_val)
          AND (p_filter_user_id IS NULL OR p.user_id = p_filter_user_id)
          AND p.status IS NULL
        ORDER BY ts_rank(p.content_fts, tsquery_val) DESC
        LIMIT CASE WHEN p_search_mode = 'vector' THEN 0 ELSE p_match_count * 3 END
    ),
    -- Combine results using RRF
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
            v.vec_similarity as similarity,
            f.fts_score as fts_rank,
            -- RRF score calculation
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
        c.similarity,
        c.fts_rank,
        c.combined_score
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT p_match_count;
END;
$function$;


-- --------------------------------------------------------
-- hybrid_match_interactions: Combines vector + FTS using RRF
-- --------------------------------------------------------
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
    tsquery_val := plainto_tsquery('english', p_query_text);

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


-- --------------------------------------------------------
-- hybrid_match_feedbacks: Combines vector + FTS using RRF
-- --------------------------------------------------------
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
    tsquery_val := plainto_tsquery('english', p_query_text);

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
        c.similarity,
        c.fts_rank,
        c.combined_score,
        c.embedding
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT p_match_count;
END;
$function$;


-- --------------------------------------------------------
-- hybrid_match_raw_feedbacks: Combines vector + FTS using RRF
-- --------------------------------------------------------
CREATE OR REPLACE FUNCTION public.hybrid_match_raw_feedbacks(
    p_query_embedding public.vector,
    p_query_text text,
    p_match_threshold double precision DEFAULT 0.7,
    p_match_count integer DEFAULT 10,
    p_search_mode text DEFAULT 'hybrid',
    p_rrf_k integer DEFAULT 60
)
RETURNS TABLE(
    raw_feedback_id bigint,
    feedback_name text,
    request_id text,
    agent_version text,
    feedback_content text,
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
    tsquery_val := plainto_tsquery('english', p_query_text);

    RETURN QUERY
    WITH
    vector_results AS (
        SELECT
            rf.raw_feedback_id,
            rf.feedback_name,
            rf.request_id,
            rf.agent_version,
            rf.feedback_content,
            rf.created_at,
            rf.embedding,
            1 - (rf.embedding <=> p_query_embedding) as vec_similarity,
            ROW_NUMBER() OVER (ORDER BY rf.embedding <=> p_query_embedding) as vec_rank
        FROM raw_feedbacks rf
        WHERE (p_search_mode = 'fts' OR 1 - (rf.embedding <=> p_query_embedding) > p_match_threshold)
        ORDER BY rf.embedding <=> p_query_embedding
        LIMIT CASE WHEN p_search_mode = 'fts' THEN 0 ELSE p_match_count * 3 END
    ),
    fts_results AS (
        SELECT
            rf.raw_feedback_id,
            rf.feedback_name,
            rf.request_id,
            rf.agent_version,
            rf.feedback_content,
            rf.created_at,
            rf.embedding,
            ts_rank(rf.feedback_content_fts, tsquery_val)::double precision as fts_score,
            ROW_NUMBER() OVER (ORDER BY ts_rank(rf.feedback_content_fts, tsquery_val) DESC) as fts_rank
        FROM raw_feedbacks rf
        WHERE (p_search_mode = 'vector' OR rf.feedback_content_fts @@ tsquery_val)
        ORDER BY ts_rank(rf.feedback_content_fts, tsquery_val) DESC
        LIMIT CASE WHEN p_search_mode = 'vector' THEN 0 ELSE p_match_count * 3 END
    ),
    combined AS (
        SELECT
            COALESCE(v.raw_feedback_id, f.raw_feedback_id) as raw_feedback_id,
            COALESCE(v.feedback_name, f.feedback_name) as feedback_name,
            COALESCE(v.request_id, f.request_id) as request_id,
            COALESCE(v.agent_version, f.agent_version) as agent_version,
            COALESCE(v.feedback_content, f.feedback_content) as feedback_content,
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
        c.feedback_name,
        c.request_id,
        c.agent_version,
        c.feedback_content,
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
