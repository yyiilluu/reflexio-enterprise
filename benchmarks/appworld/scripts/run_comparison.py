#!/usr/bin/env python3
"""
CLI script to compare baseline vs Reflexio-enhanced AppWorld results.

Can either:
1. Compare two existing result directories
2. Run the full pipeline (baseline → publish → enhanced → compare)

Usage:
    # Compare existing results
    python benchmarks/appworld/scripts/run_comparison.py \
        --baseline output/baseline --enhanced output/reflexio_enhanced

    # Full pipeline
    python benchmarks/appworld/scripts/run_comparison.py --full-pipeline \
        --model minimax/MiniMax-M2.5 --dataset dev \
        --reflexio-url http://localhost:8081 --reflexio-api-key KEY
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent.parent / ".env")

from benchmarks.appworld.config import (
    DEFAULT_MODEL,
    VALID_SPLITS,
    ExperimentConfig,
    ReflexioConfig,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Compare baseline vs Reflexio-enhanced AppWorld results."
    )

    # Comparison mode: load from existing directories
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Path to baseline results directory (containing summary.json)",
    )
    parser.add_argument(
        "--enhanced",
        type=Path,
        help="Path to enhanced results directory (containing summary.json)",
    )

    # Full pipeline mode
    parser.add_argument(
        "--full-pipeline",
        action="store_true",
        help="Run the complete pipeline (baseline → publish → enhanced → compare)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"LLM model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--dataset",
        default="dev",
        choices=VALID_SPLITS,
        help="AppWorld dataset split (default: dev)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=20,
        help="Max agent steps per task (default: 20)",
    )
    parser.add_argument(
        "--task-ids",
        nargs="+",
        help="Specific task IDs to run (default: all in split)",
    )
    parser.add_argument(
        "--reflexio-url",
        default=os.getenv("REFLEXIO_API_URL", "http://localhost:8081"),
        help="Reflexio server URL",
    )
    parser.add_argument(
        "--reflexio-api-key",
        default=os.getenv("REFLEXIO_API_KEY", ""),
        help="Reflexio API key",
    )
    parser.add_argument(
        "--skip-publish",
        action="store_true",
        help="Skip publishing to Reflexio (reuse existing data)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def compare_from_directories(baseline_dir: Path, enhanced_dir: Path) -> None:
    """
    Compare results from two existing experiment output directories.

    Args:
        baseline_dir (Path): Directory containing baseline summary.json and trace files
        enhanced_dir (Path): Directory containing enhanced summary.json and trace files
    """
    from benchmarks.appworld.evaluation.analysis import generate_report
    from benchmarks.appworld.evaluation.metrics import compute_comparison

    baseline_results = _load_results_from_dir(baseline_dir)
    enhanced_results = _load_results_from_dir(enhanced_dir)

    if not baseline_results or not enhanced_results:
        print("Error: Could not load results from one or both directories")
        sys.exit(1)

    # Print report
    report = generate_report(baseline_results, enhanced_results)
    print(report)

    # Save comparison
    comparison = compute_comparison(baseline_results, enhanced_results)
    output_path = baseline_dir.parent / "comparison.json"
    with open(output_path, "w") as f:
        json.dump(comparison, f, indent=2, default=str)
    print(f"Saved comparison to {output_path}")


def _load_results_from_dir(results_dir: Path) -> list:
    """
    Load TaskResult objects from an experiment output directory.

    Reads the summary.json file to reconstruct TaskResult objects.

    Args:
        results_dir (Path): Directory containing summary.json

    Returns:
        list: List of TaskResult objects
    """
    from benchmarks.appworld.runner.task_runner import TaskResult

    summary_path = results_dir / "summary.json"
    if not summary_path.exists():
        print(f"Error: {summary_path} not found")
        return []

    with open(summary_path) as f:
        summary = json.load(f)

    return [
        TaskResult(
            task_id=t["task_id"],
            passed=t["passed"],
            completed=t["completed"],
            total_steps=t["total_steps"],
            error_count=t["error_count"],
            elapsed_seconds=t["elapsed_seconds"],
        )
        for t in summary.get("per_task", [])
    ]


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    if args.full_pipeline:
        # Full pipeline mode
        if not args.reflexio_api_key:
            print("Error: --reflexio-api-key required for full pipeline")
            sys.exit(1)

        from benchmarks.appworld.runner.experiment_runner import run_full_pipeline

        config = ExperimentConfig(
            model=args.model,
            dataset=args.dataset,
            max_steps=args.max_steps,
            task_ids=args.task_ids,
        )
        reflexio_config = ReflexioConfig(
            api_key=args.reflexio_api_key,
            url=args.reflexio_url,
        )

        run_full_pipeline(config, reflexio_config, skip_publish=args.skip_publish)

        # Also print the full report
        from benchmarks.appworld.evaluation.analysis import generate_report

        baseline_results = _load_results_from_dir(config.output_dir / "baseline")
        enhanced_results = _load_results_from_dir(
            config.output_dir / "reflexio_enhanced"
        )
        if baseline_results and enhanced_results:
            print(generate_report(baseline_results, enhanced_results))

    elif args.baseline and args.enhanced:
        # Comparison mode
        compare_from_directories(args.baseline, args.enhanced)
    else:
        print("Error: Provide either --full-pipeline or both --baseline and --enhanced")
        sys.exit(1)


if __name__ == "__main__":
    main()
