-- Fix match_interactions function to return bigint for interaction_id
-- The interaction_id column was changed from text to bigint in migration 20251212052750

-- Drop existing function first since return type is changing (interaction_id: text -> bigint)
DROP FUNCTION IF EXISTS public.match_interactions(public.vector, double precision, integer);

CREATE OR REPLACE FUNCTION public.match_interactions(query_embedding public.vector, match_threshold double precision, match_count integer)
 RETURNS TABLE(interaction_id bigint, user_id text, content text, request_id text, created_at timestamp with time zone, user_action text, user_action_description text, interacted_image_url text, similarity double precision)
 LANGUAGE plpgsql
AS $function$
begin
    return query
    select
        interactions.interaction_id,
        interactions.user_id,
        interactions.content,
        interactions.request_id,
        interactions.created_at,
        interactions.user_action,
        interactions.user_action_description,
        interactions.interacted_image_url,
        1 - (interactions.embedding <=> query_embedding) as similarity
    from interactions
    where 1 - (interactions.embedding <=> query_embedding) > match_threshold
    order by interactions.embedding <=> query_embedding
    limit match_count;
end;
$function$;
