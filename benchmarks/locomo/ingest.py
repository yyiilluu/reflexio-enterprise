"""Ingest LoCoMo conversations into Reflexio session-by-session."""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from reflexio_commons.config_schema import (
    ProfileExtractorConfig,
    StorageConfigLocal,
)

from benchmarks.locomo.data_loader import LoCoMoSample
from reflexio.reflexio_client.reflexio import InteractionData, ReflexioClient

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


def _setup_config(client: ReflexioClient) -> None:
    """
    Configure the Reflexio server with the LoCoMo profile extractor.

    Args:
        client (ReflexioClient): Authenticated client
    """
    config = client.get_config()

    # Set up local file storage for the benchmark
    storage_dir = str(Path(__file__).resolve().parent / "reflexio_storage")
    config.storage_config = StorageConfigLocal(dir_path=storage_dir)

    config.profile_extractor_configs = [PROFILE_EXTRACTOR_CONFIG]
    # Clear feedback configs — not needed for this benchmark
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
    print(
        f"  Ingesting sample {sample.sample_id} ({len(sample.sessions)} sessions) as user_id={user_id}"
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
                    print(
                        f"    Session {session.session_id}: published {len(interactions)} turns"
                    )
                else:
                    msg = resp.message if resp else "no response"
                    print(f"    Session {session.session_id}: FAILED — {msg}")
                break  # Success or non-retryable failure
            except Exception as e:
                if "429" in str(e) and attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    print(
                        f"    Session {session.session_id}: rate limited, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    time.sleep(delay)
                else:
                    raise


def ingest_all(
    samples: list[LoCoMoSample],
    reflexio_url: str,
    reflexio_api_key: str | None = None,
    max_workers: int = 1,
) -> None:
    """
    Ingest all LoCoMo samples into Reflexio. Different samples are ingested
    in parallel; sessions within each sample are sequential.

    Args:
        samples (list[LoCoMoSample]): Parsed LoCoMo samples
        reflexio_url (str): Reflexio server URL
        reflexio_api_key (str | None): API key (falls back to env)
        max_workers (int): Max parallel ingestion threads
    """
    api_key = reflexio_api_key or os.getenv("REFLEXIO_API_KEY")
    client = ReflexioClient(api_key=api_key, url_endpoint=reflexio_url)

    print("Setting up Reflexio config...")
    _setup_config(client)

    print(f"Ingesting {len(samples)} samples (max_workers={max_workers})...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_ingest_sample, sample, client): sample.sample_id
            for sample in samples
        }
        for future in as_completed(futures):
            sample_id = futures[future]
            try:
                future.result()
                print(f"  Sample {sample_id}: done")
            except Exception as e:
                print(f"  Sample {sample_id}: ERROR — {e}")

    print("Ingestion complete.")
