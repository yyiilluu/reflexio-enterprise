-- Migration: Add atomic lock acquisition RPC function
-- This fixes the race condition in profile_generation lock acquisition

CREATE OR REPLACE FUNCTION public.try_acquire_in_progress_lock(
    p_state_key TEXT,
    p_request_id TEXT,
    p_stale_lock_seconds INT DEFAULT 300
)
RETURNS JSONB
LANGUAGE plpgsql
AS $function$
DECLARE
    v_current_state JSONB;
    v_current_time BIGINT;
BEGIN
    v_current_time := EXTRACT(EPOCH FROM NOW())::BIGINT;

    -- Use INSERT ... ON CONFLICT to atomically:
    -- 1. Insert new lock if no row exists
    -- 2. Update existing row based on lock state (stale vs active)
    INSERT INTO _operation_state (service_name, operation_state, updated_at)
    VALUES (
        p_state_key,
        jsonb_build_object(
            'in_progress', true,
            'started_at', v_current_time,
            'current_request_id', p_request_id,
            'pending_request_id', NULL::text
        ),
        NOW()
    )
    ON CONFLICT (service_name) DO UPDATE
    SET operation_state = CASE
        -- Case 1: Not in_progress - acquire lock
        WHEN NOT COALESCE((_operation_state.operation_state->>'in_progress')::boolean, false)
        THEN jsonb_build_object(
            'in_progress', true,
            'started_at', v_current_time,
            'current_request_id', p_request_id,
            'pending_request_id', NULL::text
        )
        -- Case 2: Stale lock (started > stale_lock_seconds ago) - acquire lock
        WHEN (v_current_time - COALESCE((_operation_state.operation_state->>'started_at')::bigint, 0)) >= p_stale_lock_seconds
        THEN jsonb_build_object(
            'in_progress', true,
            'started_at', v_current_time,
            'current_request_id', p_request_id,
            'pending_request_id', NULL::text
        )
        -- Case 3: Active lock - just update pending_request_id
        ELSE jsonb_set(
            _operation_state.operation_state,
            '{pending_request_id}',
            to_jsonb(p_request_id)
        )
    END,
    updated_at = NOW()
    RETURNING operation_state INTO v_current_state;

    -- Return result indicating whether we acquired the lock
    -- We acquired it if current_request_id matches our request_id
    RETURN jsonb_build_object(
        'acquired', (v_current_state->>'current_request_id') = p_request_id,
        'state', v_current_state
    );
END;
$function$;
