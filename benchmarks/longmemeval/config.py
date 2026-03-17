"""
Shared configuration and helpers for the LongMemEval benchmark pipeline.

All scripts import from this module for consistent paths, naming conventions,
and Reflexio configuration.
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from reflexio_commons.config_schema import (
    Config,
    LLMConfig,
    ProfileExtractorConfig,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BENCHMARK_DIR = Path(__file__).resolve().parent
DATA_DIR = BENCHMARK_DIR / "data"
OUTPUT_DIR = BENCHMARK_DIR / "output"
INGEST_STATE_DIR = OUTPUT_DIR / "ingest_state"
HYPOTHESES_DIR = OUTPUT_DIR / "hypotheses"
EVAL_RESULTS_DIR = OUTPUT_DIR / "eval_results"
EVAL_SCRIPTS_DIR = DATA_DIR / "eval_scripts"

# ---------------------------------------------------------------------------
# Reflexio connection
# ---------------------------------------------------------------------------
BACKEND_PORT = os.environ.get("BACKEND_PORT", "8081")
REFLEXIO_URL = f"http://localhost:{BACKEND_PORT}"

# ---------------------------------------------------------------------------
# Default models
# ---------------------------------------------------------------------------
DEFAULT_EXTRACTION_MODEL = "minimax/MiniMax-M2.5"
DEFAULT_ANSWER_MODEL = "minimax/MiniMax-M2.5"
DEFAULT_JUDGE_MODEL = "gpt-4o"

# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------


def make_user_id(variant: str, question_id: str) -> str:
    """
    Create a unique Reflexio user_id for a given LongMemEval question.

    Args:
        variant (str): Dataset variant (e.g., "oracle", "s", "m")
        question_id (str): The question identifier from LongMemEval

    Returns:
        str: A unique user_id like "lme_oracle_42"
    """
    return f"lme_{variant}_{question_id}"


def make_session_id(question_id: str, session_idx: int) -> str:
    """
    Create a unique Reflexio session_id for a given session within a question.

    Args:
        question_id (str): The question identifier
        session_idx (int): Zero-based index of the session within the question's haystack

    Returns:
        str: A session_id like "lme_42_sess_0"
    """
    return f"lme_{question_id}_sess_{session_idx}"


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

# LongMemEval date format: "2024/01/15 (Mon) 14:30" or similar
_DATE_RE = re.compile(r"(\d{4})/(\d{2})/(\d{2})\s*\(\w+\)\s*(\d{2}):(\d{2})")


def parse_longmemeval_date(date_str: str) -> int:
    """
    Parse a LongMemEval date string into a Unix timestamp.

    Args:
        date_str (str): Date in format "YYYY/MM/DD (DAY) HH:MM"

    Returns:
        int: Unix timestamp (UTC)

    Raises:
        ValueError: If the date string doesn't match the expected format
    """
    if m := _DATE_RE.match(date_str):
        year, month, day, hour, minute = (int(g) for g in m.groups())
        dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        return int(dt.timestamp())
    raise ValueError(f"Cannot parse LongMemEval date: {date_str!r}")


# ---------------------------------------------------------------------------
# Reflexio extraction config for LongMemEval
# ---------------------------------------------------------------------------

PROFILE_EXTRACTOR_CONFIG = ProfileExtractorConfig(
    extractor_name="longmemeval_facts",
    profile_content_definition_prompt=(
        "Extract ALL factual information about the user from the conversation. Include:\n"
        "- Personal facts (name, age, location, occupation, family, pets)\n"
        "- Preferences (food, music, hobbies, travel, technology)\n"
        "- Past experiences and events (trips, purchases, health events)\n"
        "- Opinions and beliefs expressed by the user\n"
        "- Plans and future intentions\n"
        "- Relationships and social connections\n"
        "- Professional details (job, workplace, skills, projects)\n"
        "- Specific numbers, dates, and quantities mentioned\n"
        "\n"
        "For each fact, include temporal context if available "
        '(e.g., "As of March 2024, user lives in Seattle").\n'
        "If the user corrects or updates a previous statement, extract the UPDATED fact "
        "noting it supersedes prior information."
    ),
    context_prompt=(
        "Conversation between a user and an AI assistant. "
        "Extract factual information about the user."
    ),
)


def make_reflexio_config() -> Config:
    """
    Build the Reflexio Config used for LongMemEval ingestion.

    Returns:
        Config: Configured for fact extraction with large windows
    """
    return Config(
        storage_config=None,
        profile_extractor_configs=[PROFILE_EXTRACTOR_CONFIG],
        extraction_window_size=100,
        extraction_window_stride=100,
        llm_config=LLMConfig(generation_model_name=DEFAULT_EXTRACTION_MODEL),
    )
