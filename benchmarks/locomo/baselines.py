"""Context retrieval strategies (baselines) for LoCoMo QA evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from benchmarks.locomo.config import DEFAULT_SEARCH_THRESHOLD, DEFAULT_TOP_K

if TYPE_CHECKING:
    from reflexio.reflexio_client.reflexio import ReflexioClient


def no_context(**_kwargs: object) -> str:
    """Return empty context."""
    return ""


def reflexio_search(
    client: ReflexioClient,
    user_id: str,
    question: str,
    **_kwargs: object,
) -> str:
    """
    Semantic search using the question as query to retrieve top-k profiles.

    Args:
        client (ReflexioClient): Reflexio client
        user_id (str): User ID used during ingestion
        question (str): The QA question to search with

    Returns:
        str: Search results formatted as a bullet list
    """
    profile_resp = client.search_profiles(
        user_id=user_id,
        query=question,
        top_k=DEFAULT_TOP_K,
        threshold=DEFAULT_SEARCH_THRESHOLD,
    )
    if not profile_resp.success or not profile_resp.user_profiles:
        return ""

    parts = ["## User Profiles"]
    parts.extend(f"- {p.profile_content}" for p in profile_resp.user_profiles)
    return "\n".join(parts)


def get_context(
    strategy: str,
    question: str,
    client: ReflexioClient | None = None,
    user_id: str = "",
) -> str:
    """
    Dispatch to the appropriate context retrieval strategy.

    Args:
        strategy (str): One of "no_context", "reflexio_search"
        question (str): The QA question
        client (ReflexioClient | None): Reflexio client (required for reflexio_* strategies)
        user_id (str): User ID (required for reflexio_* strategies)

    Returns:
        str: Context string
    """
    if strategy == "no_context":
        return no_context()
    if strategy == "reflexio_search":
        if client is None:
            raise ValueError("ReflexioClient required for reflexio_search")
        return reflexio_search(client=client, user_id=user_id, question=question)
    raise ValueError(f"Unknown strategy: {strategy}")
