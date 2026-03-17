"""
Compute Task Goal Completion (TGC), Scenario Goal Completion (SGC),
and per-task comparison metrics for AppWorld benchmark results.
"""

from collections import defaultdict

from benchmarks.appworld.runner.task_runner import TaskResult


def compute_metrics(results: list[TaskResult]) -> dict:
    """
    Compute aggregate metrics for a set of task results.

    Metrics include:
    - TGC: Percentage of tasks that passed all assertions
    - Total/passed/failed counts
    - Average steps to completion (for passed tasks)
    - Average error rate per task
    - Completion rate (agent called complete_task)

    Args:
        results (list[TaskResult]): Task results from an experiment run

    Returns:
        dict: Dictionary of computed metrics
    """
    if not results:
        return {"tgc": 0.0, "total": 0, "passed": 0, "failed": 0}

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    completed = sum(1 for r in results if r.completed)

    # Average steps for passed tasks
    passed_steps = [r.total_steps for r in results if r.passed]
    avg_steps_passed = sum(passed_steps) / len(passed_steps) if passed_steps else 0.0

    # Average steps for all tasks
    avg_steps_all = sum(r.total_steps for r in results) / total

    # Average errors
    avg_errors = sum(r.error_count for r in results) / total

    # Average time
    avg_time = sum(r.elapsed_seconds for r in results) / total

    return {
        "tgc": 100.0 * passed / total,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "completion_rate": 100.0 * completed / total,
        "avg_steps_passed": round(avg_steps_passed, 1),
        "avg_steps_all": round(avg_steps_all, 1),
        "avg_errors": round(avg_errors, 2),
        "avg_time_seconds": round(avg_time, 1),
    }


def compute_sgc(results: list[TaskResult]) -> dict:
    """
    Compute Scenario Goal Completion (SGC).

    A scenario passes only when ALL of its task instantiations pass.
    Task IDs are expected to follow AppWorld convention where the scenario
    is derived from the task ID prefix (e.g., "123_1", "123_2", "123_3"
    all belong to scenario "123").

    Args:
        results (list[TaskResult]): Task results from an experiment run

    Returns:
        dict: SGC metrics including rate, per-scenario breakdown
    """
    # Group tasks by scenario (prefix before last underscore)
    scenarios: dict[str, list[TaskResult]] = defaultdict(list)
    for r in results:
        # AppWorld task IDs: scenario_id + "_" + instantiation_id
        parts = r.task_id.rsplit("_", 1)
        scenario_id = parts[0] if len(parts) > 1 else r.task_id
        scenarios[scenario_id].append(r)

    total_scenarios = len(scenarios)
    passed_scenarios = sum(
        1 for tasks in scenarios.values() if all(t.passed for t in tasks)
    )

    per_scenario = {
        sid: {
            "passed": all(t.passed for t in tasks),
            "tasks_passed": sum(1 for t in tasks if t.passed),
            "tasks_total": len(tasks),
        }
        for sid, tasks in sorted(scenarios.items())
    }

    return {
        "sgc": 100.0 * passed_scenarios / total_scenarios if total_scenarios else 0.0,
        "total_scenarios": total_scenarios,
        "passed_scenarios": passed_scenarios,
        "per_scenario": per_scenario,
    }


def compute_comparison(
    baseline: list[TaskResult],
    enhanced: list[TaskResult],
) -> dict:
    """
    Compare baseline and enhanced experiment results.

    Computes per-task diffs (improved, regressed, unchanged) and aggregate
    metrics for both experiments.

    Args:
        baseline (list[TaskResult]): Baseline experiment results
        enhanced (list[TaskResult]): Enhanced experiment results

    Returns:
        dict: Comparison results with metrics, per-task diffs, and summary
    """
    baseline_map = {r.task_id: r for r in baseline}
    enhanced_map = {r.task_id: r for r in enhanced}

    # Compute per-task diffs
    common_ids = sorted(set(baseline_map) & set(enhanced_map))
    improved, regressed, unchanged = [], [], []

    for task_id in common_ids:
        b = baseline_map[task_id]
        e = enhanced_map[task_id]

        if not b.passed and e.passed:
            improved.append(task_id)
        elif b.passed and not e.passed:
            regressed.append(task_id)
        else:
            unchanged.append(task_id)

    # Efficiency comparison (steps for commonly-passed tasks)
    both_passed = [
        tid
        for tid in common_ids
        if baseline_map[tid].passed and enhanced_map[tid].passed
    ]
    baseline_steps = [baseline_map[tid].total_steps for tid in both_passed]
    enhanced_steps = [enhanced_map[tid].total_steps for tid in both_passed]

    baseline_metrics = compute_metrics(baseline)
    enhanced_metrics = compute_metrics(enhanced)
    baseline_sgc = compute_sgc(baseline)
    enhanced_sgc = compute_sgc(enhanced)

    return {
        "baseline_metrics": baseline_metrics,
        "enhanced_metrics": enhanced_metrics,
        "baseline_sgc": baseline_sgc,
        "enhanced_sgc": enhanced_sgc,
        "comparison": {
            "common_tasks": len(common_ids),
            "improved": improved,
            "regressed": regressed,
            "unchanged": unchanged,
            "improved_count": len(improved),
            "regressed_count": len(regressed),
            "unchanged_count": len(unchanged),
            "net_improvement": len(improved) - len(regressed),
            "tgc_delta": enhanced_metrics["tgc"] - baseline_metrics["tgc"],
            "sgc_delta": enhanced_sgc["sgc"] - baseline_sgc["sgc"],
        },
        "efficiency": {
            "both_passed_count": len(both_passed),
            "baseline_avg_steps": (
                round(sum(baseline_steps) / len(baseline_steps), 1)
                if baseline_steps
                else 0.0
            ),
            "enhanced_avg_steps": (
                round(sum(enhanced_steps) / len(enhanced_steps), 1)
                if enhanced_steps
                else 0.0
            ),
        },
    }
