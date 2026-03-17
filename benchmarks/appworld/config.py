"""
Experiment configuration for AppWorld benchmark evaluation.

Centralizes all settings: model selection, dataset splits, Reflexio configuration,
and agent hyperparameters.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# AppWorld dataset splits
VALID_SPLITS = ("dev", "test_normal", "test_challenge")

# Default model for all LLM calls
DEFAULT_MODEL = "minimax/MiniMax-M2.5"


@dataclass
class ExperimentConfig:
    """
    Configuration for a single AppWorld benchmark experiment run.

    Args:
        model (str): LLM model identifier (litellm-compatible)
        dataset (str): AppWorld dataset split to evaluate
        max_steps (int): Maximum agent reasoning steps per task
        temperature (float): LLM sampling temperature (0 for deterministic)
        experiment_name (str): Name for grouping output files
        output_dir (Path): Directory for saving results
        task_ids (list[str] | None): Specific task IDs to run (None = all in split)
    """

    model: str = DEFAULT_MODEL
    dataset: str = "dev"
    max_steps: int = 20
    temperature: float = 0.0
    experiment_name: str = "appworld_eval"
    output_dir: Path = field(default_factory=lambda: OUTPUT_DIR)
    task_ids: list[str] | None = None

    def __post_init__(self):
        if self.dataset not in VALID_SPLITS:
            raise ValueError(
                f"Invalid dataset split '{self.dataset}'. Must be one of: {VALID_SPLITS}"
            )
        self.output_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class ReflexioConfig:
    """
    Configuration for Reflexio integration in enhanced experiments.

    Args:
        api_key (str): Reflexio API key
        url (str): Reflexio server URL
        agent_version (str): Agent version tag for Reflexio tracking
        profile_top_k (int): Number of profiles to retrieve per search
        feedback_top_k (int): Number of raw feedbacks to retrieve per search
        skill_top_k (int): Number of skills to retrieve per search
        search_threshold (float): Minimum similarity threshold for search results
    """

    api_key: str = field(default_factory=lambda: os.getenv("REFLEXIO_API_KEY", ""))
    url: str = field(
        default_factory=lambda: os.getenv("REFLEXIO_API_URL", "http://localhost:8081")
    )
    agent_version: str = "appworld-v1"
    profile_top_k: int = 10
    feedback_top_k: int = 5
    skill_top_k: int = 3
    search_threshold: float = 0.1
