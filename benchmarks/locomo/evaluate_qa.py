"""Main evaluation orchestrator for LoCoMo QA benchmark."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from benchmarks.locomo.answer_generator import generate_answer
from benchmarks.locomo.baselines import get_context
from benchmarks.locomo.config import (
    CATEGORY_MAP,
    DEFAULT_MODEL,
    DEFAULT_REFLEXIO_URL,
    REFLEXIO_STRATEGIES,
)
from benchmarks.locomo.data_loader import LoCoMoSample
from benchmarks.locomo.metrics import compute_score
from reflexio.reflexio_client.reflexio import ReflexioClient

logger = logging.getLogger(__name__)


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


class QAResult:
    """Result of a single QA evaluation."""

    def __init__(
        self,
        sample_id: int,
        question: str,
        gold_answer: str,
        category: int,
        strategy: str,
        prediction: str,
        score: float,
        context_length: int,
    ):
        self.sample_id = sample_id
        self.question = question
        self.gold_answer = gold_answer
        self.category = category
        self.category_name = CATEGORY_MAP[category]
        self.strategy = strategy
        self.prediction = prediction
        self.score = score
        self.context_length = context_length

    def to_dict(self) -> dict:
        return {
            "sample_id": self.sample_id,
            "question": self.question,
            "gold_answer": self.gold_answer,
            "category": self.category,
            "category_name": self.category_name,
            "strategy": self.strategy,
            "prediction": self.prediction,
            "score": self.score,
            "context_length": self.context_length,
        }


def _load_checkpoint(output_dir: Path) -> dict[str, list[dict]]:
    """Load checkpoint results if they exist."""
    checkpoint = output_dir / "checkpoint.json"
    if checkpoint.exists():
        with checkpoint.open() as f:
            return json.load(f)
    return {}


def _save_checkpoint(output_dir: Path, results: dict[str, list[dict]]) -> None:
    """Save checkpoint results."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "checkpoint.json").open("w") as f:
        json.dump(results, f, indent=2)


def _checkpoint_key(sample_id: int, strategy: str) -> str:
    return f"{sample_id}:{strategy}"


def evaluate(
    samples: list[LoCoMoSample],
    strategies: list[str],
    model: str = DEFAULT_MODEL,
    reflexio_url: str = DEFAULT_REFLEXIO_URL,
    reflexio_api_key: str | None = None,
    output_dir: str | Path = "benchmarks/locomo/output",
) -> list[QAResult]:
    """
    Run QA evaluation across all samples and strategies.

    Args:
        samples (list[LoCoMoSample]): Parsed LoCoMo samples
        strategies (list[str]): List of strategies to evaluate
        model (str): LiteLLM model identifier
        reflexio_url (str): Reflexio server URL
        reflexio_api_key (str | None): API key
        output_dir (str | Path): Directory for checkpoints and results

    Returns:
        list[QAResult]: All evaluation results
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Set up Reflexio client if needed
    client: ReflexioClient | None = None
    needs_reflexio = any(s in REFLEXIO_STRATEGIES for s in strategies)
    if needs_reflexio:
        api_key = reflexio_api_key or os.getenv("REFLEXIO_API_KEY")
        client = ReflexioClient(api_key=api_key, url_endpoint=reflexio_url)

    # Load checkpoint
    checkpoint = _load_checkpoint(output_dir)
    all_results: list[QAResult] = []

    # Restore previously completed results
    for result_list in checkpoint.values():
        all_results.extend(
            QAResult(
                sample_id=r["sample_id"],
                question=r["question"],
                gold_answer=r["gold_answer"],
                category=r["category"],
                strategy=r["strategy"],
                prediction=r["prediction"],
                score=r["score"],
                context_length=r["context_length"],
            )
            for r in result_list
        )

    total_qa = sum(len(s.qa) for s in samples) * len(strategies)
    completed = len(all_results)
    logger.info(
        "Evaluating %d QA pairs (%d already done from checkpoint)", total_qa, completed
    )

    for sample in samples:
        user_id = f"locomo-{sample.sample_id}"
        for strategy in strategies:
            ck = _checkpoint_key(sample.sample_id, strategy)
            if ck in checkpoint:
                logger.debug(
                    "Sample %d / %s: skipping (checkpoint)",
                    sample.sample_id,
                    strategy,
                )
                continue

            logger.info(
                "Sample %d / %s: evaluating %d QAs...",
                sample.sample_id,
                strategy,
                len(sample.qa),
            )
            sample_results: list[dict] = []

            for qi, qa in enumerate(sample.qa):
                try:
                    context = get_context(
                        strategy=strategy,
                        question=qa.question,
                        client=client,
                        user_id=user_id,
                    )
                    prediction = generate_answer(
                        question=qa.question,
                        context=context,
                        speaker_a=sample.speaker_a,
                        speaker_b=sample.speaker_b,
                        model=model,
                    )
                    score = compute_score(prediction, qa.answer, qa.category)
                except Exception as e:
                    logger.error("QA %d: ERROR — %s", qi, e)
                    prediction = ""
                    score = 0.0
                    context = ""

                result = QAResult(
                    sample_id=sample.sample_id,
                    question=qa.question,
                    gold_answer=qa.answer,
                    category=qa.category,
                    strategy=strategy,
                    prediction=prediction,
                    score=score,
                    context_length=len(context),
                )
                all_results.append(result)
                sample_results.append(result.to_dict())

                logger.debug(
                    'sample_id=%d strategy=%s category=%s score=%.3f context_chars=%d question="%s"',
                    sample.sample_id,
                    strategy,
                    CATEGORY_MAP[qa.category],
                    score,
                    len(context),
                    qa.question,
                )

                if (qi + 1) % 10 == 0:
                    logger.debug("%d/%d done", qi + 1, len(sample.qa))

            # Save checkpoint after each (sample, strategy) pair
            checkpoint[ck] = sample_results
            _save_checkpoint(output_dir, checkpoint)
            avg = (
                sum(r["score"] for r in sample_results) / len(sample_results)
                if sample_results
                else 0
            )
            logger.info(
                "sample=%d strategy=%s avg_score=%.3f num_qa=%d",
                sample.sample_id,
                strategy,
                avg,
                len(sample_results),
            )

    return all_results
