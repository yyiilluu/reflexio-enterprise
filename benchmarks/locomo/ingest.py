"""Ingest LoCoMo conversations into Reflexio session-by-session."""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from reflexio_commons.config_schema import (
    AgentFeedbackConfig,
    ProfileExtractorConfig,
    StorageConfigLocal,
)

from benchmarks.locomo.data_loader import LoCoMoSample
from reflexio.reflexio_client.reflexio import InteractionData, ReflexioClient

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_BASE_DELAY = 10  # seconds


def _find_env_file() -> Path | None:
    """Search for .env file starting from the benchmarks dir up to the repo root."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        env_path = current / ".env"
        if env_path.exists():
            return env_path
        current = current.parent
    return None


load_dotenv(dotenv_path=_find_env_file())

PROFILE_EXTRACTOR_CONFIG = ProfileExtractorConfig(
    extractor_name="locomo_memory",
    profile_content_definition_prompt=(
        "Extract key personal information about both speakers: names, occupations, "
        "family, hobbies, preferences, life events, travel, health, relationships, "
        "dates, and any factual details mentioned."
    ),
    context_prompt="Long-term conversation between two friends over multiple sessions.",
    extraction_window_size_override=50,
    extraction_window_stride_override=1,
)

FEEDBACK_EXTRACTOR_CONFIG = AgentFeedbackConfig(
    feedback_name="locomo_feedback",
    feedback_definition_prompt=(
        "Extract actionable observations about the conversation: patterns in behavior, "
        "recurring topics, notable changes in preferences or circumstances, "
        "and any factual details that could help answer future questions."
    ),
    extraction_window_size_override=50,
    extraction_window_stride_override=1,
)


def _setup_config(client: ReflexioClient, *, enable_feedbacks: bool = False) -> None:
    """
    Configure the Reflexio server with the LoCoMo profile extractor
    and optionally the feedback extractor.

    Args:
        client (ReflexioClient): Authenticated client
        enable_feedbacks (bool): If True, also configure feedback extraction
    """
    config = client.get_config()

    # Set up local file storage for the benchmark
    storage_dir = str(Path(__file__).resolve().parent / "reflexio_storage")
    config.storage_config = StorageConfigLocal(dir_path=storage_dir)

    config.profile_extractor_configs = [PROFILE_EXTRACTOR_CONFIG]
    if enable_feedbacks:
        config.agent_feedback_configs = [FEEDBACK_EXTRACTOR_CONFIG]
    else:
        config.agent_feedback_configs = []
    resp = client.set_config(config)
    if not resp.get("success"):
        raise RuntimeError(f"Failed to set Reflexio config: {resp.get('msg')}")


def _ingest_sample(
    sample: LoCoMoSample,
    client: ReflexioClient,
) -> None:
    """
    Ingest one LoCoMo sample (all sessions sequentially).

    Args:
        sample (LoCoMoSample): Conversation sample
        client (ReflexioClient): Authenticated client
    """
    user_id = f"locomo-{sample.sample_id}"
    logger.info(
        "Ingesting sample %d (%d sessions) as user_id=%s",
        sample.sample_id,
        len(sample.sessions),
        user_id,
    )

    for session in sample.sessions:
        interactions: list[InteractionData] = []
        for turn in session.turns:
            # Map speaker_a → User, speaker_b → Assistant
            role = "User" if turn.speaker == sample.speaker_a else "Assistant"
            interactions.append(InteractionData(role=role, content=turn.text))

        session_id = f"locomo-{sample.sample_id}-session_{session.session_id}"

        # Retry with exponential backoff on rate limit errors
        for attempt in range(MAX_RETRIES):
            try:
                resp = client.publish_interaction(
                    user_id=user_id,
                    interactions=interactions,
                    source="locomo-benchmark",
                    session_id=session_id,
                    wait_for_response=True,
                )
                if resp and resp.success:
                    logger.debug(
                        "Session %s: published %d turns",
                        session.session_id,
                        len(interactions),
                    )
                else:
                    msg = resp.message if resp else "no response"
                    logger.error("Session %s: FAILED — %s", session.session_id, msg)
                break  # Success or non-retryable failure
            except Exception as e:
                if "429" in str(e) and attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        "Session %s: rate limited, retrying in %ds (attempt %d/%d)",
                        session.session_id,
                        delay,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                    time.sleep(delay)
                else:
                    raise


def ingest_all(
    samples: list[LoCoMoSample],
    reflexio_url: str,
    reflexio_api_key: str | None = None,
    max_workers: int = 1,
    enable_feedbacks: bool = False,
) -> None:
    """
    Ingest all LoCoMo samples into Reflexio. Different samples are ingested
    in parallel; sessions within each sample are sequential.

    Args:
        samples (list[LoCoMoSample]): Parsed LoCoMo samples
        reflexio_url (str): Reflexio server URL
        reflexio_api_key (str | None): API key (falls back to env)
        max_workers (int): Max parallel ingestion threads
        enable_feedbacks (bool): If True, enable feedback extraction alongside profiles
    """
    api_key = reflexio_api_key or os.getenv("REFLEXIO_API_KEY")
    client = ReflexioClient(api_key=api_key, url_endpoint=reflexio_url)

    logger.info("Setting up Reflexio config...")
    _setup_config(client, enable_feedbacks=enable_feedbacks)

    logger.info("Ingesting %d samples (max_workers=%d)...", len(samples), max_workers)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_ingest_sample, sample, client): sample.sample_id
            for sample in samples
        }
        for future in as_completed(futures):
            sample_id = futures[future]
            try:
                future.result()
                logger.info("Sample %d: done", sample_id)
            except Exception as e:
                logger.error("Sample %d: ERROR — %s", sample_id, e)

    logger.info("Ingestion complete.")
