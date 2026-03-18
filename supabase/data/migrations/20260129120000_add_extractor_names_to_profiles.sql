-- Add extractor_names column to profiles table
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS extractor_names json;

-- Drop existing functions so we can change return types/parameters
DROP FUNCTION IF EXISTS public.match_profiles(public.vector, double precision, integer, bigint, text);
DROP FUNCTION IF EXISTS public.match_profiles(public.vector, double precision, integer, bigint, text, text);
DROP FUNCTION IF EXISTS public.hybrid_match_profiles(public.vector, text, double precision, integer, bigint, text, text, integer);
DROP FUNCTION IF EXISTS public.hybrid_match_profiles(public.vector, text, double precision, integer, bigint, text, text, integer, text);

-- Recreate match_profiles RPC to include extractor_names
CREATE OR REPLACE FUNCTION public.match_profiles(
    query_embedding public.vector,
    match_threshold double precision,
    match_count integer,
    current_epoch bigint,
    filter_user_id text DEFAULT NULL,
    filter_extractor_name text DEFAULT NULL
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
    extractor_names json,
    similarity double precision
)
LANGUAGE plpgsql
AS $function$
begin
    return query
    select
        profiles.profile_id,
        profiles.user_id,
        profiles.content,
        profiles.last_modified_timestamp,
        profiles.generated_from_request_id,
        profiles.profile_time_to_live,
        profiles.expiration_timestamp,
        profiles.custom_features,
        profiles.source,
        profiles.extractor_names,
        1 - (profiles.embedding <=> query_embedding) as similarity
    from profiles
    where profiles.expiration_timestamp >= current_epoch
    and 1 - (profiles.embedding <=> query_embedding) > match_threshold
    and (filter_user_id IS NULL OR profiles.user_id = filter_user_id)
    and (filter_extractor_name IS NULL OR profiles.extractor_names::jsonb @> to_jsonb(filter_extractor_name))
    order by profiles.embedding <=> query_embedding
    limit match_count;
end;
$function$;

-- Recreate hybrid_match_profiles RPC to include extractor_names
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
            COALESCE(v.extractor_names, f.extractor_names) as extractor_names,
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
        c.extractor_names,
        c.similarity,
        c.fts_rank,
        c.combined_score
    FROM combined c
    ORDER BY c.combined_score DESC
    LIMIT p_match_count;
END;
$function$;
