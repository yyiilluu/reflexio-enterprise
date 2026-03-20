"""CLI entry point for the LoCoMo benchmark."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `benchmarks.*` imports work
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from dotenv import load_dotenv


def _find_env_file() -> Path | None:
    """Search for .env file starting from repo root upward."""
    current = _repo_root
    for _ in range(10):
        env_path = current / ".env"
        if env_path.exists():
            return env_path
        current = current.parent
    return None


load_dotenv(dotenv_path=_find_env_file())

from benchmarks.locomo.config import (
    DEFAULT_MODEL,
    DEFAULT_REFLEXIO_URL,
    NON_REFLEXIO_STRATEGIES,
    STRATEGIES,
)
from benchmarks.locomo.data_loader import load_locomo
from benchmarks.locomo.evaluate_qa import evaluate
from benchmarks.locomo.ingest import ingest_all
from benchmarks.locomo.report import save_report

logger = logging.getLogger(__name__)


_LOG_DIR = Path(__file__).resolve().parent / "logs"


def _setup_logging(verbose: bool = False) -> None:
    """
    Configure root logger to write to both stdout and a timestamped log file.

    Args:
        verbose (bool): If True, set level to DEBUG; otherwise INFO
    """
    from datetime import datetime, timezone

    level = logging.DEBUG if verbose else logging.INFO
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    stdout_handler.setFormatter(fmt)
    root.addHandler(stdout_handler)

    # File handler — one log file per run
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(_LOG_DIR / f"run_{timestamp}.log")
    file_handler.setLevel(logging.DEBUG)  # always capture full detail in file
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the LoCoMo QA benchmark against Reflexio and baselines.",
    )
    parser.add_argument(
        "--data-file",
        default="benchmarks/locomo/data/locomo10.json",
        help="Path to locomo10.json",
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=["all"],
        choices=STRATEGIES + ["all"],
        help="Strategies to evaluate (default: all)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"LiteLLM model for answer generation (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--reflexio-url",
        default=DEFAULT_REFLEXIO_URL,
        help=f"Reflexio server URL (default: {DEFAULT_REFLEXIO_URL})",
    )
    parser.add_argument(
        "--reflexio-api-key",
        default=None,
        help="Reflexio API key (default: from REFLEXIO_API_KEY env var)",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip ingestion (use when data is already in Reflexio)",
    )
    parser.add_argument(
        "--ingest-workers",
        type=int,
        default=1,
        help="Max parallel ingestion threads (default: 1)",
    )
    parser.add_argument(
        "--output-dir",
        default="benchmarks/locomo/output",
        help="Output directory for results",
    )
    parser.add_argument(
        "--samples",
        type=int,
        nargs="+",
        default=None,
        help="Specific sample IDs to evaluate (default: all)",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Max number of samples to use (first N; for quick testing)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _setup_logging(verbose=args.verbose)

    # Resolve strategies
    strategies = list(STRATEGIES) if "all" in args.strategies else args.strategies

    # Resolve Reflexio API key: CLI arg > env var
    reflexio_api_key = args.reflexio_api_key or os.getenv("REFLEXIO_API_KEY") or None

    # Validate: Reflexio strategies require a valid API key
    needs_reflexio = any(s not in NON_REFLEXIO_STRATEGIES for s in strategies)
    if needs_reflexio and not reflexio_api_key:
        logger.error(
            "Reflexio strategies require an API key. "
            "Provide --reflexio-api-key <key> or set REFLEXIO_API_KEY env var. "
            "Or run with --strategies no_context to skip Reflexio."
        )
        sys.exit(1)

    # Load data
    logger.info("Loading data from %s...", args.data_file)
    samples = load_locomo(args.data_file)
    logger.info("Loaded %d samples", len(samples))

    # Filter samples by ID if requested
    if args.samples is not None:
        samples = [s for s in samples if s.sample_id in args.samples]
        logger.info(
            "Filtered to %d samples: %s", len(samples), [s.sample_id for s in samples]
        )

    # Truncate to max-samples for quick testing
    if args.max_samples is not None:
        if args.samples is not None:
            logger.warning(
                "Both --samples and --max-samples specified; "
                "truncating the filtered set to %d",
                args.max_samples,
            )
        samples = samples[: args.max_samples]
        logger.info("Using %d sample(s) after --max-samples", len(samples))

    logger.info("Strategies: %s", strategies)
    logger.info("Model: %s", args.model)
    if needs_reflexio:
        logger.info("Reflexio URL: %s", args.reflexio_url)

    # Ingestion
    if not args.skip_ingest and needs_reflexio:
        logger.info("=== Ingestion Phase ===")
        ingest_all(
            samples=samples,
            reflexio_url=args.reflexio_url,
            reflexio_api_key=reflexio_api_key,
            max_workers=args.ingest_workers,
        )
    elif needs_reflexio:
        logger.info("Skipping ingestion (--skip-ingest)")

    # Evaluation
    logger.info("=== Evaluation Phase ===")
    results = evaluate(
        samples=samples,
        strategies=strategies,
        model=args.model,
        reflexio_url=args.reflexio_url,
        reflexio_api_key=reflexio_api_key,
        output_dir=args.output_dir,
    )

    # Report
    logger.info("=== Report ===")
    save_report(results, args.output_dir)


if __name__ == "__main__":
    main()
