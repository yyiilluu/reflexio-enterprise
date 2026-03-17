"""
Orchestrates full AppWorld benchmark experiments: baseline, publish, enhanced, compare.

Implements the four-phase pipeline:
1. Baseline — run all tasks with BaseAppWorldAgent
2. Publish — convert traces to Reflexio interactions and publish
3. Enhanced — run same tasks with ReflexioAppWorldAgent
4. Compare — compute TGC/SGC diffs and statistical significance
"""

import json
import logging
import time
from pathlib import Path

from benchmarks.appworld.agent.base_agent import BaseAppWorldAgent
from benchmarks.appworld.agent.reflexio_agent import ReflexioAppWorldAgent
from benchmarks.appworld.config import ExperimentConfig, ReflexioConfig
from benchmarks.appworld.evaluation.metrics import compute_comparison, compute_metrics
from benchmarks.appworld.integration.reflexio_bridge import (
    publish_trace_to_reflexio,
    setup_reflexio_config,
)
from benchmarks.appworld.runner.task_runner import TaskResult, run_task

logger = logging.getLogger(__name__)


def get_task_ids(dataset: str) -> list[str]:
    """
    Get task IDs for the specified AppWorld dataset split.

    Args:
        dataset (str): Dataset split name (dev, test_normal, test_challenge)

    Returns:
        list[str]: List of task ID strings
    """
    from appworld import AppWorld

    return AppWorld.get_task_ids(dataset)


def run_experiment(
    config: ExperimentConfig,
    agent: BaseAppWorldAgent,
    label: str,
) -> list[TaskResult]:
    """
    Run an experiment on a set of AppWorld tasks with the given agent.

    Args:
        config (ExperimentConfig): Experiment configuration
        agent (BaseAppWorldAgent): Agent to use for solving tasks
        label (str): Label for this experiment run (e.g., "baseline", "enhanced")

    Returns:
        list[TaskResult]: Results for all tasks
    """
    task_ids = config.task_ids or get_task_ids(config.dataset)
    output_dir = config.output_dir / label
    output_dir.mkdir(parents=True, exist_ok=True)

    experiment_name = f"{config.experiment_name}_{label}"

    logger.info(
        "Running %s experiment: %d tasks, model=%s, max_steps=%d",
        label,
        len(task_ids),
        config.model,
        config.max_steps,
    )

    results = []
    start_time = time.time()

    for i, task_id in enumerate(task_ids, 1):
        logger.info("[%d/%d] Task %s", i, len(task_ids), task_id)
        result = run_task(
            task_id=task_id,
            agent=agent,
            experiment_name=experiment_name,
            output_dir=output_dir,
        )
        results.append(result)

        # Log running stats
        passed_so_far = sum(1 for r in results if r.passed)
        logger.info(
            "  Progress: %d/%d completed, %d/%d passed (%.1f%%)",
            i,
            len(task_ids),
            passed_so_far,
            i,
            100 * passed_so_far / i,
        )

    elapsed = time.time() - start_time
    logger.info(
        "%s experiment complete: %d tasks in %.1f minutes",
        label,
        len(results),
        elapsed / 60,
    )

    # Save summary
    _save_results_summary(results, output_dir / "summary.json", config, label)
    return results


def run_baseline(config: ExperimentConfig) -> list[TaskResult]:
    """
    Run the baseline experiment (no Reflexio context).

    Args:
        config (ExperimentConfig): Experiment configuration

    Returns:
        list[TaskResult]: Baseline results
    """
    agent = BaseAppWorldAgent(
        model=config.model,
        max_steps=config.max_steps,
        temperature=config.temperature,
    )
    return run_experiment(config, agent, "baseline")


def publish_to_reflexio(
    results: list[TaskResult],
    reflexio_config: ReflexioConfig,
) -> int:
    """
    Publish all baseline traces to Reflexio for profile/feedback extraction.

    Reads saved trace files, converts to InteractionData, and publishes
    with synchronous extraction.

    Args:
        results (list[TaskResult]): Baseline task results with trace file paths
        reflexio_config (ReflexioConfig): Reflexio connection settings

    Returns:
        int: Number of successfully published traces
    """
    from reflexio.reflexio_client.reflexio import ReflexioClient

    client = ReflexioClient(
        api_key=reflexio_config.api_key,
        url_endpoint=reflexio_config.url,
    )
    setup_reflexio_config(client)

    published = 0
    for i, result in enumerate(results, 1):
        if not result.trace_file:
            logger.warning("No trace file for task %s, skipping", result.task_id)
            continue

        # Load trace data to get instruction and supervisor info
        trace_data = _load_trace_data(result.trace_file)
        if not trace_data:
            continue

        logger.info("[%d/%d] Publishing task %s", i, len(results), result.task_id)

        # Reconstruct minimal trace for bridge
        from benchmarks.appworld.agent.base_agent import AgentTrace, StepRecord

        steps = [
            StepRecord(
                step=s["step"],
                code=s["code"],
                output=s["output"],
                error=s["error"],
                timestamp=s["timestamp"],
            )
            for s in trace_data.get("trace", {}).get("steps", [])
        ]
        trace = AgentTrace(
            task_id=result.task_id,
            steps=steps,
            completed=result.completed,
            total_steps=result.total_steps,
        )

        # Get task info from AppWorld
        task_instruction, supervisor_email, supervisor_name = _get_task_info(
            result.task_id
        )

        success = publish_trace_to_reflexio(
            client=client,
            trace=trace,
            task_instruction=task_instruction,
            supervisor_email=supervisor_email,
            supervisor_name=supervisor_name,
            agent_version=reflexio_config.agent_version,
            task_passed=result.passed,
        )
        if success:
            published += 1

    logger.info("Published %d/%d traces to Reflexio", published, len(results))
    return published


def run_enhanced(
    config: ExperimentConfig,
    reflexio_config: ReflexioConfig,
) -> list[TaskResult]:
    """
    Run the enhanced experiment (with Reflexio context injection).

    Args:
        config (ExperimentConfig): Experiment configuration
        reflexio_config (ReflexioConfig): Reflexio connection settings

    Returns:
        list[TaskResult]: Enhanced results
    """
    from reflexio.reflexio_client.reflexio import ReflexioClient

    client = ReflexioClient(
        api_key=reflexio_config.api_key,
        url_endpoint=reflexio_config.url,
    )

    agent = ReflexioAppWorldAgent(
        model=config.model,
        client=client,
        reflexio_config=reflexio_config,
        max_steps=config.max_steps,
        temperature=config.temperature,
    )
    return run_experiment(config, agent, "reflexio_enhanced")


def run_full_pipeline(
    config: ExperimentConfig,
    reflexio_config: ReflexioConfig,
    skip_publish: bool = False,
) -> dict:
    """
    Run the complete four-phase evaluation pipeline.

    Phase 1: Baseline run (no memory)
    Phase 2: Publish baseline traces to Reflexio
    Phase 3: Enhanced run (with Reflexio context)
    Phase 4: Compare results

    Args:
        config (ExperimentConfig): Experiment configuration
        reflexio_config (ReflexioConfig): Reflexio connection settings
        skip_publish (bool): Skip publishing to Reflexio (use existing data)

    Returns:
        dict: Comparison results with metrics and per-task breakdown
    """
    # Phase 1: Baseline
    print(f"\n[Phase 1/4] Running baseline ({config.dataset}, {config.model})...")
    baseline_results = run_baseline(config)

    # Phase 2: Publish to Reflexio
    if not skip_publish:
        print("\n[Phase 2/4] Publishing to Reflexio...")
        published = publish_to_reflexio(baseline_results, reflexio_config)
        print(f"  Published {published}/{len(baseline_results)} traces")
    else:
        print("\n[Phase 2/4] Skipping publish (using existing Reflexio data)")

    # Phase 3: Enhanced
    print(f"\n[Phase 3/4] Running enhanced ({config.dataset}, {config.model})...")
    enhanced_results = run_enhanced(config, reflexio_config)

    # Phase 4: Compare
    print("\n[Phase 4/4] Computing comparison metrics...")
    comparison = compute_comparison(baseline_results, enhanced_results)

    # Save comparison
    comparison_path = config.output_dir / "comparison.json"
    with open(comparison_path, "w") as f:
        json.dump(comparison, f, indent=2, default=str)
    print(f"  Saved comparison to {comparison_path}")

    return comparison


def _get_task_info(task_id: str) -> tuple[str, str, str]:
    """
    Get task instruction and supervisor info from AppWorld.

    Args:
        task_id (str): AppWorld task identifier

    Returns:
        tuple[str, str, str]: (instruction, supervisor_email, supervisor_name)
    """
    try:
        from appworld import AppWorld

        with AppWorld(task_id=task_id, experiment_name="__info__") as world:
            instruction = world.task.instruction
            email = ""
            name = ""
            if hasattr(world.task, "supervisor") and world.task.supervisor:
                sup = world.task.supervisor
                email = getattr(sup, "email", "")
                first = getattr(sup, "first_name", "")
                last = getattr(sup, "last_name", "")
                name = f"{first} {last}".strip()
            return instruction, email, name
    except Exception:
        logger.exception("Failed to get task info for %s", task_id)
        return f"Task {task_id}", "", ""


def _load_trace_data(trace_file: str) -> dict | None:
    """
    Load trace data from a JSON file.

    Args:
        trace_file (str): Path to the trace JSON file

    Returns:
        dict | None: Parsed trace data or None on failure
    """
    try:
        with open(trace_file) as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load trace file: %s", trace_file)
        return None


def _save_results_summary(
    results: list[TaskResult],
    filepath: Path,
    config: ExperimentConfig,
    label: str,
) -> None:
    """
    Save experiment results summary to a JSON file.

    Args:
        results (list[TaskResult]): All task results
        filepath (Path): Output file path
        config (ExperimentConfig): Experiment configuration
        label (str): Experiment label
    """
    metrics = compute_metrics(results)
    summary = {
        "label": label,
        "model": config.model,
        "dataset": config.dataset,
        "max_steps": config.max_steps,
        "total_tasks": len(results),
        "metrics": metrics,
        "per_task": [
            {
                "task_id": r.task_id,
                "passed": r.passed,
                "completed": r.completed,
                "total_steps": r.total_steps,
                "error_count": r.error_count,
                "elapsed_seconds": r.elapsed_seconds,
            }
            for r in results
        ],
    }
    with open(filepath, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Saved summary to %s", filepath)
