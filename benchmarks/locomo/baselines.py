"""Context retrieval strategies (baselines) for LoCoMo QA evaluation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from benchmarks.locomo.config import (
    DEFAULT_REFLEXIO_URL,
    DEFAULT_SEARCH_THRESHOLD,
    DEFAULT_TOP_K,
    NON_REFLEXIO_STRATEGIES,
)

if TYPE_CHECKING:
    from benchmarks.locomo.data_loader import LoCoMoSession
    from reflexio.reflexio_client.reflexio import ReflexioClient

logger = logging.getLogger(__name__)


def no_context(**_kwargs: object) -> str:
    """Return empty context."""
    return ""


def reflexio_base(
    client: ReflexioClient,
    user_id: str,
    question: str,
    **_kwargs: object,
) -> str:
    """
    Semantic search using the question as query to retrieve top-k profiles only.

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


def reflexio_enhanced(
    reflexio_url: str,
    api_key: str,
    user_id: str,
    question: str,
    **_kwargs: object,
) -> str:
    """
    Unified search using profiles + feedbacks via the /api/search endpoint.

    Args:
        reflexio_url (str): Reflexio server base URL
        api_key (str): API key for authentication
        user_id (str): User ID used during ingestion
        question (str): The QA question to search with

    Returns:
        str: Combined profiles and feedbacks context
    """
    resp = httpx.post(
        f"{reflexio_url}/api/search",
        json={
            "query": question,
            "user_id": user_id,
            "top_k": DEFAULT_TOP_K,
            "threshold": DEFAULT_SEARCH_THRESHOLD,
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if not data.get("success"):
        logger.warning("Unified search failed: %s", data.get("msg"))
        return ""

    parts: list[str] = []

    # Profiles section
    if profiles := data.get("profiles"):
        parts.append("## User Profiles")
        parts.extend(f"- {p['profile_content']}" for p in profiles)

    # Feedbacks section (aggregated + raw)
    feedback_items = [f"- {fb['feedback_content']}" for fb in data.get("feedbacks", [])]
    feedback_items.extend(
        f"- {rfb['feedback_content']}" for rfb in data.get("raw_feedbacks", [])
    )

    if feedback_items:
        parts.append("## Feedbacks")
        parts.extend(feedback_items)

    return "\n".join(parts)


def full_context(
    sessions: list[LoCoMoSession],
    speaker_a: str,
    speaker_b: str,
    **_kwargs: object,
) -> str:
    """
    Return the full conversation text as context (upper-bound baseline).

    Args:
        sessions (list[LoCoMoSession]): All conversation sessions
        speaker_a (str): Name of speaker A
        speaker_b (str): Name of speaker B

    Returns:
        str: Full conversation formatted with session headers
    """
    parts: list[str] = []
    for session in sessions:
        parts.append(f"### Session {session.session_id} ({session.date_time})")
        for turn in session.turns:
            name = speaker_a if turn.speaker == speaker_a else speaker_b
            parts.append(f"{name}: {turn.text}")
        parts.append("")  # blank line between sessions
    return "\n".join(parts)


def get_context(
    strategy: str,
    question: str,
    client: ReflexioClient | None = None,
    user_id: str = "",
    reflexio_url: str = DEFAULT_REFLEXIO_URL,
    reflexio_api_key: str = "",
    sessions: list[LoCoMoSession] | None = None,
    speaker_a: str = "",
    speaker_b: str = "",
) -> str:
    """
    Dispatch to the appropriate context retrieval strategy.

    Args:
        strategy (str): One of the registered strategy names
        question (str): The QA question
        client (ReflexioClient | None): Reflexio client (required for reflexio_base)
        user_id (str): User ID (required for reflexio_* strategies)
        reflexio_url (str): Reflexio server URL (required for reflexio_enhanced)
        reflexio_api_key (str): API key (required for reflexio_enhanced)
        sessions (list[LoCoMoSession] | None): Conversation sessions
            (required for full_context)
        speaker_a (str): Name of speaker A (required for full_context)
        speaker_b (str): Name of speaker B (required for full_context)

    Returns:
        str: Context string
    """
    if strategy in NON_REFLEXIO_STRATEGIES and strategy != "full_context":
        return no_context()

    match strategy:
        case "no_context":
            return no_context()
        case "reflexio_base":
            if client is None:
                raise ValueError("ReflexioClient required for reflexio_base")
            return reflexio_base(client=client, user_id=user_id, question=question)
        case "reflexio_enhanced":
            if not reflexio_api_key:
                raise ValueError("API key required for reflexio_enhanced")
            return reflexio_enhanced(
                reflexio_url=reflexio_url,
                api_key=reflexio_api_key,
                user_id=user_id,
                question=question,
            )
        case "full_context":
            if not sessions:
                raise ValueError("Sessions required for full_context")
            return full_context(
                sessions=sessions, speaker_a=speaker_a, speaker_b=speaker_b
            )
        case _:
            raise ValueError(f"Unknown strategy: {strategy}")
