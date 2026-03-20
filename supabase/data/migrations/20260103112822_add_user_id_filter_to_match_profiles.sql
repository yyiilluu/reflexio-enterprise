-- Add user_id filter to match_profiles function
-- This fixes a bug where search_profiles was returning profiles from all users
-- instead of filtering by the specified user_id

CREATE OR REPLACE FUNCTION public.match_profiles(
    query_embedding public.vector,
    match_threshold double precision,
    match_count integer,
    current_epoch bigint,
    filter_user_id text DEFAULT NULL
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
        1 - (profiles.embedding <=> query_embedding) as similarity
    from profiles
    where profiles.expiration_timestamp >= current_epoch
    and 1 - (profiles.embedding <=> query_embedding) > match_threshold
    and (filter_user_id IS NULL OR profiles.user_id = filter_user_id)
    order by profiles.embedding <=> query_embedding
    limit match_count;
end;
$function$;
