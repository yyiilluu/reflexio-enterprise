"""CLI entry point for the LoCoMo benchmark."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Force unbuffered output so progress is visible in real-time
os.environ["PYTHONUNBUFFERED"] = "1"

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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Resolve strategies
    strategies = list(STRATEGIES) if "all" in args.strategies else args.strategies

    # Resolve Reflexio API key: CLI arg > env var
    reflexio_api_key = args.reflexio_api_key or os.getenv("REFLEXIO_API_KEY") or None

    # Validate: Reflexio strategies require a valid API key
    needs_reflexio = any(s not in NON_REFLEXIO_STRATEGIES for s in strategies)
    if needs_reflexio and not reflexio_api_key:
        print(
            "Error: Reflexio strategies require an API key.\n"
            "  Provide --reflexio-api-key <key> or set REFLEXIO_API_KEY env var.\n"
            "  Or run with --strategies no_context full_context to skip Reflexio."
        )
        sys.exit(1)

    # Load data
    print(f"Loading data from {args.data_file}...")
    samples = load_locomo(args.data_file)
    print(f"Loaded {len(samples)} samples")

    # Filter samples if requested
    if args.samples is not None:
        samples = [s for s in samples if s.sample_id in args.samples]
        print(f"Filtered to {len(samples)} samples: {[s.sample_id for s in samples]}")

    print(f"Strategies: {strategies}")
    print(f"Model: {args.model}")
    if needs_reflexio:
        print(f"Reflexio URL: {args.reflexio_url}")

    # Ingestion
    if not args.skip_ingest and needs_reflexio:
        print("\n=== Ingestion Phase ===")
        ingest_all(
            samples=samples,
            reflexio_url=args.reflexio_url,
            reflexio_api_key=reflexio_api_key,
            max_workers=args.ingest_workers,
        )
    elif needs_reflexio:
        print("Skipping ingestion (--skip-ingest)")

    # Evaluation
    print("\n=== Evaluation Phase ===")
    results = evaluate(
        samples=samples,
        strategies=strategies,
        model=args.model,
        reflexio_url=args.reflexio_url,
        reflexio_api_key=reflexio_api_key,
        output_dir=args.output_dir,
    )

    # Report
    print("\n=== Report ===")
    save_report(results, args.output_dir)


if __name__ == "__main__":
    main()
