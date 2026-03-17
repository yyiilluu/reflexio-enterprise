#!/usr/bin/env python3
"""
Unified CLI entry point for the AppWorld benchmark evaluation pipeline.

Runs the full end-to-end pipeline: baseline -> publish -> enhanced -> compare -> report.
Mirrors the LoCoMo benchmark runner pattern with a single command.

Usage:
    # Full pipeline (requires running Reflexio server)
    python benchmarks/appworld/run_benchmark.py

    # Baseline only (no Reflexio needed)
    python benchmarks/appworld/run_benchmark.py --baseline-only

    # Skip publishing (reuse existing Reflexio data)
    python benchmarks/appworld/run_benchmark.py --skip-publish

    # Specific tasks
    python benchmarks/appworld/run_benchmark.py --task-ids 123_1 456_2

    # Custom model and dataset split
    python benchmarks/appworld/run_benchmark.py --model gpt-4o --dataset test_normal
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from benchmarks.appworld.config import ExperimentConfig, ReflexioConfig

# Force unbuffered output so print() appears immediately in logs
os.environ["PYTHONUNBUFFERED"] = "1"

# Add repo root to sys.path so `benchmarks.appworld.*` imports work
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger(__name__)


def _find_env_file() -> Path | None:
    """
    Walk up from repo root to find a .env file.

    Returns:
        Path | None: Path to .env file, or None if not found
    """
    candidate = _REPO_ROOT / ".env"
    if candidate.exists():
        return candidate
    return None


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the unified benchmark runner."""
    parser = argparse.ArgumentParser(
        description="AppWorld Benchmark — unified pipeline runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline with defaults
  python benchmarks/appworld/run_benchmark.py

  # Baseline only (no Reflexio server needed)
  python benchmarks/appworld/run_benchmark.py --baseline-only

  # Skip publishing (reuse existing Reflexio data from prior run)
  python benchmarks/appworld/run_benchmark.py --skip-publish

  # Run specific tasks with a different model
  python benchmarks/appworld/run_benchmark.py --model gpt-4o --task-ids 123_1 456_2

  # Use test_normal split with more steps
  python benchmarks/appworld/run_benchmark.py --dataset test_normal --max-steps 30
""",
    )
    parser.add_argument(
        "--dataset",
        default="dev",
        choices=("dev", "test_normal", "test_challenge"),
        help="AppWorld dataset split (default: dev)",
    )
    parser.add_argument(
        "--model",
        default="minimax/MiniMax-M2.5",
        help="LiteLLM model identifier (default: minimax/MiniMax-M2.5)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=20,
        help="Max agent reasoning steps per task (default: 20)",
    )
    parser.add_argument(
        "--task-ids",
        nargs="+",
        help="Specific task IDs to run (default: all in split)",
    )
    parser.add_argument(
        "--reflexio-url",
        default=None,
        help="Reflexio server URL (default: $REFLEXIO_API_URL or http://localhost:8081)",
    )
    parser.add_argument(
        "--reflexio-api-key",
        default=None,
        help="Reflexio API key (default: $REFLEXIO_API_KEY)",
    )
    parser.add_argument(
        "--skip-publish",
        action="store_true",
        help="Skip publishing traces to Reflexio (reuse existing data)",
    )
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="Run baseline only — no Reflexio server needed",
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


def _resolve_reflexio_config(
    args: argparse.Namespace,
) -> ReflexioConfig:
    """
    Build a ReflexioConfig from CLI args and environment variables.

    Args:
        args (argparse.Namespace): Parsed CLI arguments

    Returns:
        ReflexioConfig: Validated Reflexio configuration

    Raises:
        SystemExit: If API key is missing and Reflexio is required
    """
    from benchmarks.appworld.config import ReflexioConfig

    api_key = args.reflexio_api_key or os.getenv("REFLEXIO_API_KEY", "")
    url = args.reflexio_url or os.getenv("REFLEXIO_API_URL", "http://localhost:8081")

    if not api_key:
        print("Error: Reflexio API key is required for the full pipeline.")
        print("  Set REFLEXIO_API_KEY environment variable or pass --reflexio-api-key")
        sys.exit(1)

    return ReflexioConfig(api_key=api_key, url=url)


def run_baseline_phase(config: ExperimentConfig) -> list:
    """
    Phase 1: Run baseline experiment (no Reflexio context).

    Args:
        config (ExperimentConfig): Experiment configuration

    Returns:
        list: Baseline TaskResult list
    """
    from benchmarks.appworld.runner.experiment_runner import run_baseline

    return run_baseline(config)


def run_publish_phase(
    results: list,
    reflexio_config: ReflexioConfig,
) -> int:
    """
    Phase 2: Publish baseline traces to Reflexio.

    Args:
        results (list): Baseline TaskResult list
        reflexio_config (ReflexioConfig): Reflexio connection settings

    Returns:
        int: Number of successfully published traces
    """
    from benchmarks.appworld.runner.experiment_runner import publish_to_reflexio

    return publish_to_reflexio(results, reflexio_config)


def run_enhanced_phase(
    config: ExperimentConfig,
    reflexio_config: ReflexioConfig,
) -> list:
    """
    Phase 3: Run enhanced experiment (with Reflexio context).

    Args:
        config (ExperimentConfig): Experiment configuration
        reflexio_config (ReflexioConfig): Reflexio connection settings

    Returns:
        list: Enhanced TaskResult list
    """
    from benchmarks.appworld.runner.experiment_runner import run_enhanced

    return run_enhanced(config, reflexio_config)


def run_report_phase(
    baseline_results: list,
    enhanced_results: list,
    output_dir: Path,
) -> dict:
    """
    Phase 4: Compute comparison metrics and generate report.

    Args:
        baseline_results (list): Baseline TaskResult list
        enhanced_results (list): Enhanced TaskResult list
        output_dir (Path): Directory to save results

    Returns:
        dict: Comparison metrics dictionary
    """
    from benchmarks.appworld.evaluation.analysis import generate_report
    from benchmarks.appworld.evaluation.metrics import compute_comparison

    comparison = compute_comparison(baseline_results, enhanced_results)

    # Save comparison JSON
    comparison_path = output_dir / "comparison.json"
    with open(comparison_path, "w") as f:
        json.dump(comparison, f, indent=2, default=str)

    # Generate and print human-readable report
    report = generate_report(baseline_results, enhanced_results)
    print(report)

    # Save report text
    report_path = output_dir / "report.txt"
    with open(report_path, "w") as f:
        f.write(report)

    print(f"\n  Saved comparison JSON: {comparison_path}")
    print(f"  Saved report text:    {report_path}")

    return comparison


def run_baseline_only_report(results: list, output_dir: Path) -> None:
    """
    Print a summary report for baseline-only mode.

    Args:
        results (list): Baseline TaskResult list
        output_dir (Path): Directory where results were saved
    """
    from benchmarks.appworld.evaluation.metrics import compute_metrics, compute_sgc

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
    print(f"\n  Results saved to: {output_dir / 'baseline'}")


def main() -> None:
    """Run the AppWorld benchmark pipeline."""
    args = parse_args()

    # Load .env
    if env_path := _find_env_file():
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_path)

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    # Deferred import to keep --help fast
    from benchmarks.appworld.config import ExperimentConfig

    # Build experiment config
    config = ExperimentConfig(
        model=args.model,
        dataset=args.dataset,
        max_steps=args.max_steps,
        task_ids=args.task_ids,
    )
    if args.output_dir:
        config.output_dir = args.output_dir

    # Determine number of phases
    total_phases = 2 if args.baseline_only else 4

    pipeline_start = time.time()

    print("=" * 70)
    print("  APPWORLD BENCHMARK")
    print(f"  Model:   {config.model}")
    print(f"  Dataset: {config.dataset}")
    print(f"  Steps:   {config.max_steps}")
    if config.task_ids:
        print(f"  Tasks:   {len(config.task_ids)} specified")
    print(f"  Mode:    {'baseline-only' if args.baseline_only else 'full pipeline'}")
    print(f"  Output:  {config.output_dir}")
    print("=" * 70)

    # Validate Reflexio config if needed
    reflexio_config = None
    if not args.baseline_only:
        reflexio_config = _resolve_reflexio_config(args)
        print(f"  Reflexio: {reflexio_config.url}")

    # --- Phase 1: Baseline ---
    print(
        f"\n[Phase 1/{total_phases}] Running baseline ({config.dataset}, {config.model})..."
    )
    baseline_results = run_baseline_phase(config)
    baseline_passed = sum(1 for r in baseline_results if r.passed)
    print(
        f"  Baseline complete: {baseline_passed}/{len(baseline_results)} passed "
        f"({100 * baseline_passed / len(baseline_results):.1f}% TGC)"
    )

    if args.baseline_only:
        # --- Phase 2 (baseline-only): Report ---
        print(f"\n[Phase 2/{total_phases}] Generating baseline report...")
        run_baseline_only_report(baseline_results, config.output_dir)
    else:
        # --- Phase 2: Publish ---
        if args.skip_publish:
            print(
                f"\n[Phase 2/{total_phases}] Skipping publish (using existing Reflexio data)"
            )
        else:
            print(f"\n[Phase 2/{total_phases}] Publishing traces to Reflexio...")
            published = run_publish_phase(baseline_results, reflexio_config)
            print(f"  Published {published}/{len(baseline_results)} traces")

        # --- Phase 3: Enhanced ---
        print(
            f"\n[Phase 3/{total_phases}] Running enhanced ({config.dataset}, {config.model})..."
        )
        enhanced_results = run_enhanced_phase(config, reflexio_config)
        enhanced_passed = sum(1 for r in enhanced_results if r.passed)
        print(
            f"  Enhanced complete: {enhanced_passed}/{len(enhanced_results)} passed "
            f"({100 * enhanced_passed / len(enhanced_results):.1f}% TGC)"
        )

        # --- Phase 4: Report ---
        print(f"\n[Phase 4/{total_phases}] Generating comparison report...")
        run_report_phase(baseline_results, enhanced_results, config.output_dir)

    elapsed = time.time() - pipeline_start
    print(f"\nTotal pipeline time: {elapsed / 60:.1f} minutes")


if __name__ == "__main__":
    main()
