#!/usr/bin/env python3
"""
CLI script to run the Reflexio-enhanced AppWorld experiment.

Requires a running Reflexio server with previously published baseline data.

Usage:
    python benchmarks/appworld/scripts/run_enhanced.py \
        --reflexio-url http://localhost:8081 --reflexio-api-key KEY

    python benchmarks/appworld/scripts/run_enhanced.py \
        --model gpt-4o --dataset test_normal \
        --reflexio-url http://localhost:8081 --reflexio-api-key KEY
"""

import argparse
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
from benchmarks.appworld.evaluation.metrics import compute_metrics, compute_sgc
from benchmarks.appworld.runner.experiment_runner import run_enhanced


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Reflexio-enhanced AppWorld experiment."
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
        default="appworld_enhanced",
        help="Experiment name for grouping outputs",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: benchmarks/appworld/output)",
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
        "--agent-version",
        default="appworld-v1",
        help="Agent version tag for Reflexio (default: appworld-v1)",
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

    if not args.reflexio_api_key:
        print("Error: --reflexio-api-key is required (or set REFLEXIO_API_KEY env var)")
        sys.exit(1)

    config = ExperimentConfig(
        model=args.model,
        dataset=args.dataset,
        max_steps=args.max_steps,
        experiment_name=args.experiment_name,
        task_ids=args.task_ids,
    )
    if args.output_dir:
        config.output_dir = args.output_dir

    reflexio_config = ReflexioConfig(
        api_key=args.reflexio_api_key,
        url=args.reflexio_url,
        agent_version=args.agent_version,
    )

    print(f"Running enhanced: model={config.model}, dataset={config.dataset}")
    print(f"  Reflexio: {reflexio_config.url}")

    results = run_enhanced(config, reflexio_config)

    # Print summary
    metrics = compute_metrics(results)
    sgc = compute_sgc(results)

    print("\n" + "=" * 60)
    print("  ENHANCED RESULTS")
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
