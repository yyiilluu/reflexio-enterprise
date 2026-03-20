"""
Unified search service that searches across all entity types in parallel.

Executes in two phases:
  Phase A: Query rewriting + embedding generation (parallel)
  Phase B: Entity searches across profiles, feedbacks, raw_feedbacks, skills (parallel)
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

from reflexio_commons.api_schema.retriever_schema import (
    ConversationTurn,
    RewrittenQuery,
    SearchUserProfileRequest,
    UnifiedSearchRequest,
    UnifiedSearchResponse,
)
from reflexio_commons.api_schema.service_schemas import (
    Feedback,
    RawFeedback,
    Skill,
    UserProfile,
)
from reflexio_commons.config_schema import APIKeyConfig

from reflexio.server.prompt.prompt_manager import PromptManager
from reflexio.server.services.query_rewriter import QueryRewriter
from reflexio.server.services.storage.storage_base import BaseStorage
from reflexio.server.site_var.feature_flags import is_skill_generation_enabled

logger = logging.getLogger(__name__)


def run_unified_search(
    request: UnifiedSearchRequest,
    org_id: str,
    storage: BaseStorage,
    api_key_config: APIKeyConfig | None,
    prompt_manager: PromptManager,
) -> UnifiedSearchResponse:
    """
    Search across all entity types (profiles, feedbacks, raw_feedbacks, skills) in parallel.

    Phase A runs query rewriting and embedding generation in parallel.
    Phase B runs all entity searches in parallel using the results from Phase A.
    Skills search is gated behind the skill_generation feature flag.

    Args:
        request (UnifiedSearchRequest): The unified search request
        org_id (str): Organization ID (used for feature flag checks)
        storage: Storage instance (SupabaseStorage or compatible)
        api_key_config (APIKeyConfig): API key configuration for LLM calls
        prompt_manager (PromptManager): Prompt manager for query rewriter

    Returns:
        UnifiedSearchResponse: Combined results from all entity types
    """
    if not request.query:
        return UnifiedSearchResponse(success=True, msg="No query provided")

    top_k = request.top_k if request.top_k is not None else 5
    threshold = request.threshold if request.threshold is not None else 0.3

    # --- Phase A: parallel query rewrite + embedding generation ---
    supports_embedding = hasattr(storage, "_get_embedding")
    rewritten_query, embedding = _run_phase_a(
        query=request.query,
        org_id=org_id,
        storage=storage,
        api_key_config=api_key_config,  # type: ignore[reportArgumentType]
        prompt_manager=prompt_manager,
        supports_embedding=supports_embedding,
        conversation_history=request.conversation_history,
        query_rewrite=bool(request.query_rewrite),
    )

    rewritten_query_text = rewritten_query.fts_query

    # --- Phase B: parallel searches across all entity types ---
    profiles, feedbacks, raw_feedbacks, skills = _run_phase_b(
        request=request,
        org_id=org_id,
        storage=storage,
        embedding=embedding,
        query=rewritten_query_text,
        top_k=top_k,
        threshold=threshold,
    )

    if profiles is None:
        return UnifiedSearchResponse(success=False, msg="Search failed")

    return UnifiedSearchResponse(
        success=True,
        profiles=profiles,
        feedbacks=feedbacks,  # type: ignore[reportArgumentType]
        raw_feedbacks=raw_feedbacks,  # type: ignore[reportArgumentType]
        skills=skills,  # type: ignore[reportArgumentType]
        rewritten_query=rewritten_query_text
        if rewritten_query_text != request.query
        else None,
    )


def _run_phase_a(
    query: str,
    org_id: str,  # noqa: ARG001
    storage: BaseStorage,
    api_key_config: APIKeyConfig,
    prompt_manager: PromptManager,
    supports_embedding: bool = True,
    conversation_history: list[ConversationTurn] | None = None,
    query_rewrite: bool = False,
) -> tuple[RewrittenQuery, list[float] | None]:
    """Run query rewriting and embedding generation in parallel.

    Args:
        query (str): The original search query
        org_id (str): Organization ID
        storage (BaseStorage): Storage instance
        api_key_config (APIKeyConfig): API key configuration
        prompt_manager (PromptManager): Prompt manager instance
        supports_embedding (bool): Whether the storage backend supports embedding generation.
            When False, skips embedding and returns None (local/self-host storage).
        conversation_history (list, optional): Prior conversation turns for context-aware query rewriting
        query_rewrite (bool): Whether query rewriting is enabled for this request

    Returns:
        tuple[RewrittenQuery, Optional[list[float]]]: (RewrittenQuery, embedding_vector) — embedding is None when unsupported or on failure
    """
    query_rewriter = QueryRewriter(
        api_key_config=api_key_config,
        prompt_manager=prompt_manager,
    )

    rewritten_query = None
    embedding = None

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        rewrite_future = executor.submit(
            query_rewriter.rewrite,
            query,
            query_rewrite,
            conversation_history,
        )

        embedding_future = None
        if supports_embedding:
            embedding_future = executor.submit(storage._get_embedding, query)  # type: ignore[reportAttributeAccessIssue]

        try:
            rewritten_query = rewrite_future.result(timeout=10)
        except Exception as e:
            logger.warning("Query rewrite failed: %s", e)
            rewritten_query = RewrittenQuery(fts_query=query)

        if embedding_future is not None:
            try:
                embedding = embedding_future.result(timeout=10)
            except Exception as e:
                logger.error("Embedding generation failed: %s", e)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return rewritten_query, embedding


def _run_phase_b(
    request: UnifiedSearchRequest,
    org_id: str,
    storage: BaseStorage,
    embedding: list[float] | None,
    query: str,
    top_k: int,
    threshold: float,
) -> tuple[
    list[UserProfile] | None,
    list[Feedback] | None,
    list[RawFeedback] | None,
    list[Skill] | None,
]:
    """Run parallel searches across all entity types by delegating to storage methods.

    Args:
        request (UnifiedSearchRequest): The search request (for filters)
        org_id (str): Organization ID
        storage (BaseStorage): Storage instance
        embedding (Optional[list[float]]): Pre-computed query embedding, or None for text-only search
        query (str): Query string (possibly rewritten) for FTS
        top_k (int): Maximum results per entity type
        threshold (float): Minimum match threshold

    Returns:
        tuple: (profiles, feedbacks, raw_feedbacks, skills) — all None on timeout/failure
    """
    skills_enabled = is_skill_generation_enabled(org_id)

    executor = ThreadPoolExecutor(max_workers=4)
    try:
        profiles_future = executor.submit(
            _search_profiles_via_storage,
            storage,
            query,
            top_k,
            threshold,
            request.user_id,
            embedding,
        )
        feedbacks_future = executor.submit(
            storage.search_feedbacks,
            query=query,
            agent_version=request.agent_version,
            feedback_name=request.feedback_name,
            status_filter=[None],
            match_threshold=threshold,
            match_count=top_k,
            query_embedding=embedding,
        )
        raw_feedbacks_future = executor.submit(
            storage.search_raw_feedbacks,
            query=query,
            user_id=request.user_id,
            agent_version=request.agent_version,
            feedback_name=request.feedback_name,
            status_filter=[None],
            match_threshold=threshold,
            match_count=top_k,
            query_embedding=embedding,
        )
        skills_future = (
            executor.submit(
                storage.search_skills,
                query=query,
                feedback_name=request.feedback_name,
                agent_version=request.agent_version,
                match_threshold=threshold,
                match_count=top_k,
                query_embedding=embedding,
            )
            if skills_enabled
            else None
        )

        profiles = profiles_future.result(timeout=30)
        feedbacks = feedbacks_future.result(timeout=30)
        raw_feedbacks = raw_feedbacks_future.result(timeout=30)
        skills = skills_future.result(timeout=30) if skills_future else []
    except FuturesTimeoutError:
        logger.error("Unified search timed out")
        return None, None, None, None
    except Exception as e:
        logger.error("Unified search failed: %s", e)
        return None, None, None, None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return profiles, feedbacks, raw_feedbacks, skills


def _search_profiles_via_storage(
    storage: BaseStorage,
    query: str,
    top_k: int,
    threshold: float,
    user_id: str | None,
    embedding: list[float] | None,
) -> list[UserProfile]:
    """Search profiles via storage.search_user_profile, returning [] on error or missing user_id.

    Args:
        storage (BaseStorage): Storage instance
        query (str): Search query text
        top_k (int): Maximum results
        threshold (float): Minimum match threshold
        user_id (Optional[str]): User ID filter (required for profile search)
        embedding (Optional[list[float]]): Pre-computed query embedding, or None for text-only search

    Returns:
        list[UserProfile]: Matching profiles, or [] on error/missing user_id
    """
    if not user_id:
        return []
    try:
        return storage.search_user_profile(
            SearchUserProfileRequest(
                user_id=user_id,
                query=query,
                top_k=top_k,
                threshold=threshold,
            ),
            status_filter=[None],
            query_embedding=embedding,
        )
    except Exception as e:
        logger.error("Profile search failed: %s", e)
        return []
