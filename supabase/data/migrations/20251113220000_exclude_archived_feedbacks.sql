-- Update match_feedbacks function to exclude archived feedbacks
CREATE OR REPLACE FUNCTION public.match_feedbacks(query_embedding public.vector, match_threshold double precision, match_count integer)
 RETURNS TABLE(feedback_id bigint, feedback_name text, feedback_content text, feedback_status text, agent_version text, feedback_metadata text, created_at timestamp with time zone, similarity double precision, embedding public.vector)
 LANGUAGE plpgsql
AS $function$
begin
    return query
    select
        feedbacks.feedback_id,
        feedbacks.feedback_name,
        feedbacks.feedback_content,
        feedbacks.feedback_status,
        feedbacks.agent_version,
        feedbacks.feedback_metadata,
        feedbacks.created_at,
        1 - (feedbacks.embedding <=> query_embedding) as similarity,
        feedbacks.embedding
    from feedbacks
    where 1 - (feedbacks.embedding <=> query_embedding) > match_threshold
    and feedbacks.status is null
    order by feedbacks.embedding <=> query_embedding
    limit match_count;
end;
$function$;
