-- Add skills table for storing synthesized agent skills
-- Skills are generated from aggregated feedbacks and represent reusable behavioral rules

-- Increase maintenance_work_mem for GIN index creation
SET LOCAL maintenance_work_mem = '128MB';

-- ================================================
-- STEP 1: Create skills table
-- ================================================

CREATE TABLE public.skills (
    skill_id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    org_id text NOT NULL,
    skill_name text NOT NULL,
    description text DEFAULT '',
    version text DEFAULT '1.0.0',
    agent_version text DEFAULT '',
    feedback_name text DEFAULT '',
    instructions text DEFAULT '',
    allowed_tools jsonb DEFAULT '[]'::jsonb,
    blocking_issues jsonb DEFAULT '[]'::jsonb,
    raw_feedback_ids jsonb DEFAULT '[]'::jsonb,
    skill_status text DEFAULT 'draft',
    embedding vector(512),
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- ================================================
-- STEP 2: Add generated tsvector column for FTS
-- ================================================

ALTER TABLE public.skills ADD COLUMN content_fts tsvector
GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(instructions, '') || ' ' || coalesce(description, ''))
) STORED;

-- ================================================
-- STEP 3: Create indexes
-- ================================================

-- GIN index for full-text search
CREATE INDEX idx_skills_content_fts ON public.skills USING GIN (content_fts);

-- Composite indexes for common query patterns
CREATE INDEX idx_skills_org_feedback_name ON public.skills (org_id, feedback_name);
CREATE INDEX idx_skills_org_agent_version ON public.skills (org_id, agent_version);
CREATE INDEX idx_skills_org_skill_status ON public.skills (org_id, skill_status);

-- ================================================
-- STEP 4: Hybrid search RPC function
-- ================================================

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
    -- Convert text query to tsquery for FTS
    tsquery_val := plainto_tsquery('english', p_query_text);

    RETURN QUERY
    WITH
    -- Vector search results with ranking
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
    -- FTS results with ranking
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
    -- Combine results using Reciprocal Rank Fusion (RRF)
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
            -- RRF score calculation
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

-- ================================================
-- STEP 5: Row Level Security
-- ================================================

ALTER TABLE public.skills ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all access to skills"
    ON public.skills
    FOR ALL
    USING (true)
    WITH CHECK (true);
