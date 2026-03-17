"""Context retrieval strategies (baselines) for LoCoMo QA evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from benchmarks.locomo.config import DEFAULT_SEARCH_THRESHOLD, DEFAULT_TOP_K

if TYPE_CHECKING:
    from benchmarks.locomo.data_loader import LoCoMoSample
    from reflexio.reflexio_client.reflexio import ReflexioClient


def no_context(**_kwargs: object) -> str:
    """Return empty context."""
    return ""


def full_context(sample: LoCoMoSample, **_kwargs: object) -> str:
    """
    Concatenate all sessions into a single context string with date headers.

    Args:
        sample (LoCoMoSample): The conversation sample

    Returns:
        str: Full conversation text
    """
    parts: list[str] = []
    for session in sample.sessions:
        header = f"[Session {session.session_id}"
        if session.date_time:
            header += f" - {session.date_time}"
        header += "]"
        parts.append(header)
        parts.extend(f"{turn.speaker}: {turn.text}" for turn in session.turns)
        parts.append("")  # blank line between sessions
    return "\n".join(parts)


def reflexio_profiles(
    client: ReflexioClient,
    user_id: str,
    **_kwargs: object,
) -> str:
    """
    Retrieve all Reflexio profiles for the user and format as bullet list.

    Args:
        client (ReflexioClient): Reflexio client
        user_id (str): User ID used during ingestion

    Returns:
        str: Formatted profile context
    """
    resp = client.get_profiles(user_id=user_id, top_k=200)
    if not resp.success or not resp.user_profiles:
        return ""
    lines = [f"- {p.profile_content}" for p in resp.user_profiles]
    return "\n".join(lines)


def reflexio_search(
    client: ReflexioClient,
    user_id: str,
    question: str,
    **_kwargs: object,
) -> str:
    """
    Semantic search using the question as query. Combine top-k profiles + top-k interactions.

    Args:
        client (ReflexioClient): Reflexio client
        user_id (str): User ID used during ingestion
        question (str): The QA question to search with

    Returns:
        str: Combined search results
    """
    parts: list[str] = []

    # Search profiles
    profile_resp = client.search_profiles(
        user_id=user_id,
        query=question,
        top_k=DEFAULT_TOP_K,
        threshold=DEFAULT_SEARCH_THRESHOLD,
    )
    if profile_resp.success and profile_resp.user_profiles:
        parts.append("## User Profiles")
        parts.extend(f"- {p.profile_content}" for p in profile_resp.user_profiles)

    # Search interactions
    interaction_resp = client.search_interactions(
        user_id=user_id,
        query=question,
        top_k=DEFAULT_TOP_K,
    )
    if interaction_resp.success and interaction_resp.interactions:
        parts.append("\n## Relevant Interactions")
        parts.extend(
            f"- [{inter.role}] {inter.content}"
            for inter in interaction_resp.interactions
        )

    return "\n".join(parts)


def get_context(
    strategy: str,
    sample: LoCoMoSample,
    question: str,
    client: ReflexioClient | None = None,
    user_id: str = "",
) -> str:
    """
    Dispatch to the appropriate context retrieval strategy.

    Args:
        strategy (str): One of "no_context", "full_context", "reflexio_profiles", "reflexio_search"
        sample (LoCoMoSample): The conversation sample
        question (str): The QA question
        client (ReflexioClient | None): Reflexio client (required for reflexio_* strategies)
        user_id (str): User ID (required for reflexio_* strategies)

    Returns:
        str: Context string
    """
    if strategy == "no_context":
        return no_context()
    if strategy == "full_context":
        return full_context(sample=sample)
    if strategy == "reflexio_profiles":
        if client is None:
            raise ValueError("ReflexioClient required for reflexio_profiles")
        return reflexio_profiles(client=client, user_id=user_id)
    if strategy == "reflexio_search":
        if client is None:
            raise ValueError("ReflexioClient required for reflexio_search")
        return reflexio_search(client=client, user_id=user_id, question=question)
    raise ValueError(f"Unknown strategy: {strategy}")
