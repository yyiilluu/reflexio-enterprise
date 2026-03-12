# /user_profiler/reflexio/reflexio_client
Description: Python SDK for remote async access to Reflexio API

## Main Entry Points

- **Client**: `reflexio/client.py` - `ReflexioClient`
- **Utils**: `reflexio/client_utils.py` - Helper utilities

## Purpose

1. **Remote API access** - Async SDK for applications to call Reflexio backend
2. **Authentication** - Handle API key and Bearer token management
3. **Type-safe interface** - Auto-parsing responses into Pydantic models

## API Methods

**Authentication:**
- API key authentication via constructor or `REFLEXIO_API_KEY` env var

**Publishing:**
- `publish_interaction(request_id, user_id, interactions, source, agent_version)` - Publish interactions (triggers profile/feedback/evaluation)

**Profiles:**
- `search_profiles(request)` - Semantic search
- `get_profiles(request)` - Get all for user
- `get_all_profiles(limit, status_filter)` - Get all profiles across all users
- `delete_profile(user_id, profile_id, search_query)` - Delete profiles
- `get_profile_change_log()` - Get history
- `rerun_profile_generation(request)` - Regenerate profiles from interactions

**Interactions:**
- `search_interactions(request)` - Semantic search
- `get_interactions(request)` - Get all for user
- `delete_interaction(user_id, interaction_id)` - Delete interaction

**Requests:**
- `get_requests(request)` - Get sessions with associated interactions
- `delete_request(request_id)` - Delete a request and its interactions
- `delete_session(session_id)` - Delete all requests in a session

**Feedback:**
- `get_raw_feedbacks(request)` - Raw feedback from interactions
- `add_raw_feedback(request)` - Add raw feedback directly to storage
- `get_feedbacks(request)` - Aggregated feedback with status
- `rerun_feedback_generation(request)` - Regenerate feedback for agent version
- `run_feedback_aggregation(request)` - Aggregate raw feedbacks into insights

**Evaluation:**
- `get_agent_success_evaluation_results(request)` - Get agent success evaluation results

**Configuration:**
- `set_config(config)` - Update org config (extractors, evaluators, storage)
- `get_config()` - Get current config

## Architecture Pattern

- **All async** - Uses `aiohttp` for HTTP requests
- **Type-safe** - Pydantic models from `reflexio_commons`
- **Auto-parsing** - Responses → Pydantic models
- **Flexible input** - Accepts Pydantic models or dicts
- **Bearer auth** - Automatic token handling
