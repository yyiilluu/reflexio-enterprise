#!/usr/bin/env python3
"""
CLI script to run the baseline AppWorld experiment (no Reflexio context).

Usage:
    python benchmarks/appworld/scripts/run_baseline.py
    python benchmarks/appworld/scripts/run_baseline.py --model gpt-4o --dataset test_normal
    python benchmarks/appworld/scripts/run_baseline.py --task-ids 123_1 123_2 --max-steps 30
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from benchmarks.appworld.config import DEFAULT_MODEL, VALID_SPLITS, ExperimentConfig
from benchmarks.appworld.evaluation.metrics import compute_metrics, compute_sgc
from benchmarks.appworld.runner.experiment_runner import run_baseline


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run baseline AppWorld experiment (no Reflexio context)."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"LLM model identifier (default: {DEFAULT_MODEL})",
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
        "--experiment-name",
        default="appworld_baseline",
        help="Experiment name for grouping outputs",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: benchmarks/appworld/output)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    config = ExperimentConfig(
        model=args.model,
        dataset=args.dataset,
        max_steps=args.max_steps,
        experiment_name=args.experiment_name,
        task_ids=args.task_ids,
    )
    if args.output_dir:
        config.output_dir = args.output_dir

    print(
        f"Running baseline: model={config.model}, dataset={config.dataset}, max_steps={config.max_steps}"
    )

    results = run_baseline(config)

    # Print summary
    metrics = compute_metrics(results)
    sgc = compute_sgc(results)

    print("\n" + "=" * 60)
    print("  BASELINE RESULTS")
    print("=" * 60)
    print(f"  TGC:  {metrics['tgc']:.1f}% ({metrics['passed']}/{metrics['total']})")
    print(
        f"  SGC:  {sgc['sgc']:.1f}% ({sgc['passed_scenarios']}/{sgc['total_scenarios']})"
    )
    print(f"  Completion rate: {metrics['completion_rate']:.1f}%")
    print(f"  Avg steps (passed): {metrics['avg_steps_passed']}")
    print(f"  Avg steps (all):    {metrics['avg_steps_all']}")
    print(f"  Avg errors:         {metrics['avg_errors']}")
    print(f"  Avg time:           {metrics['avg_time_seconds']:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
