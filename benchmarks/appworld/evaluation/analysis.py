"""
Statistical analysis for comparing baseline vs enhanced AppWorld results.

Provides McNemar's test for paired binary outcomes, confusion matrix,
and stratified analysis by difficulty level and app type.
"""

import logging
from dataclasses import dataclass

from benchmarks.appworld.runner.task_runner import TaskResult

logger = logging.getLogger(__name__)


@dataclass
class StatisticalResult:
    """
    Result of a statistical comparison test.

    Args:
        test_name (str): Name of the statistical test
        statistic (float): Test statistic value
        p_value (float): P-value of the test
        significant (bool): Whether p < 0.05
        effect_size (float): Effect size measure
        details (dict): Additional test-specific details
    """

    test_name: str
    statistic: float
    p_value: float
    significant: bool
    effect_size: float
    details: dict


def mcnemar_test(
    baseline: list[TaskResult],
    enhanced: list[TaskResult],
) -> StatisticalResult:
    """
    Perform McNemar's test for paired binary outcomes.

    Tests whether the proportion of tasks that changed from pass→fail
    is significantly different from fail→pass.

    The 2x2 contingency table:
                    Enhanced Pass    Enhanced Fail
    Baseline Pass      a (both pass)    b (regressed)
    Baseline Fail      c (improved)     d (both fail)

    McNemar's test focuses on the discordant pairs (b vs c).

    Args:
        baseline (list[TaskResult]): Baseline results
        enhanced (list[TaskResult]): Enhanced results

    Returns:
        StatisticalResult: Test results with p-value and significance
    """
    baseline_map = {r.task_id: r.passed for r in baseline}
    enhanced_map = {r.task_id: r.passed for r in enhanced}
    common_ids = sorted(set(baseline_map) & set(enhanced_map))

    # Build contingency counts
    a = b = c = d = 0
    for task_id in common_ids:
        bp, ep = baseline_map[task_id], enhanced_map[task_id]
        if bp and ep:
            a += 1  # both pass
        elif bp and not ep:
            b += 1  # regressed
        elif not bp and ep:
            c += 1  # improved
        else:
            d += 1  # both fail

    # McNemar's test statistic (with continuity correction)
    discordant = b + c
    if discordant == 0:
        return StatisticalResult(
            test_name="McNemar's test",
            statistic=0.0,
            p_value=1.0,
            significant=False,
            effect_size=0.0,
            details={
                "contingency": {
                    "both_pass": a,
                    "regressed": b,
                    "improved": c,
                    "both_fail": d,
                },
                "note": "No discordant pairs — cannot compute test",
            },
        )

    # Use scipy if available, fall back to manual computation
    try:
        from scipy.stats import chi2

        chi2_stat = (abs(b - c) - 1) ** 2 / (b + c)
        p_value = 1 - chi2.cdf(chi2_stat, df=1)
    except ImportError:
        import math

        chi2_stat = (abs(b - c) - 1) ** 2 / (b + c)
        # Approximate p-value using chi2 with 1 df
        # P(X > x) ≈ erfc(sqrt(x/2)) for chi2(1)
        p_value = math.erfc(math.sqrt(chi2_stat / 2))

    # Effect size: odds ratio of discordant pairs
    effect_size = c / b if b > 0 else float("inf")

    return StatisticalResult(
        test_name="McNemar's test (continuity-corrected)",
        statistic=round(chi2_stat, 4),
        p_value=round(p_value, 6),
        significant=p_value < 0.05,
        effect_size=round(effect_size, 3),
        details={
            "contingency": {
                "both_pass": a,
                "regressed": b,
                "improved": c,
                "both_fail": d,
            },
            "total_tasks": len(common_ids),
            "discordant_pairs": discordant,
        },
    )


def confusion_matrix(
    baseline: list[TaskResult],
    enhanced: list[TaskResult],
) -> dict:
    """
    Build a confusion matrix of task outcomes between baseline and enhanced.

    Args:
        baseline (list[TaskResult]): Baseline results
        enhanced (list[TaskResult]): Enhanced results

    Returns:
        dict: Confusion matrix with counts and task ID lists
    """
    baseline_map = {r.task_id: r.passed for r in baseline}
    enhanced_map = {r.task_id: r.passed for r in enhanced}
    common_ids = sorted(set(baseline_map) & set(enhanced_map))

    categories: dict[str, list[str]] = {
        "both_pass": [],
        "regressed": [],
        "improved": [],
        "both_fail": [],
    }

    for task_id in common_ids:
        bp, ep = baseline_map[task_id], enhanced_map[task_id]
        if bp and ep:
            categories["both_pass"].append(task_id)
        elif bp and not ep:
            categories["regressed"].append(task_id)
        elif not bp and ep:
            categories["improved"].append(task_id)
        else:
            categories["both_fail"].append(task_id)

    return {
        category: {"count": len(task_ids), "task_ids": task_ids}
        for category, task_ids in categories.items()
    }


def stratified_analysis(
    baseline: list[TaskResult],
    enhanced: list[TaskResult],
) -> dict:
    """
    Stratify comparison results by task difficulty and scenario type.

    Difficulty is inferred from the dataset split encoded in task IDs.
    Scenario type groups tasks by their scenario prefix.

    Args:
        baseline (list[TaskResult]): Baseline results
        enhanced (list[TaskResult]): Enhanced results

    Returns:
        dict: Per-stratum TGC and improvement rates
    """
    baseline_map = {r.task_id: r for r in baseline}
    enhanced_map = {r.task_id: r for r in enhanced}
    common_ids = sorted(set(baseline_map) & set(enhanced_map))

    # Group by scenario prefix
    scenario_groups: dict[str, list[str]] = {}
    for task_id in common_ids:
        parts = task_id.rsplit("_", 1)
        scenario = parts[0] if len(parts) > 1 else task_id
        scenario_groups.setdefault(scenario, []).append(task_id)

    strata = {}
    for scenario, task_ids in sorted(scenario_groups.items()):
        b_passed = sum(1 for tid in task_ids if baseline_map[tid].passed)
        e_passed = sum(1 for tid in task_ids if enhanced_map[tid].passed)
        total = len(task_ids)
        strata[scenario] = {
            "total": total,
            "baseline_passed": b_passed,
            "enhanced_passed": e_passed,
            "baseline_tgc": round(100.0 * b_passed / total, 1),
            "enhanced_tgc": round(100.0 * e_passed / total, 1),
            "tgc_delta": round(100.0 * (e_passed - b_passed) / total, 1),
        }

    return strata


def generate_report(
    baseline: list[TaskResult],
    enhanced: list[TaskResult],
) -> str:
    """
    Generate a human-readable comparison report.

    Args:
        baseline (list[TaskResult]): Baseline results
        enhanced (list[TaskResult]): Enhanced results

    Returns:
        str: Formatted report string
    """
    from benchmarks.appworld.evaluation.metrics import (
        compute_comparison,
    )

    comparison = compute_comparison(baseline, enhanced)
    stat = mcnemar_test(baseline, enhanced)
    cm = confusion_matrix(baseline, enhanced)

    lines = [
        "=" * 70,
        "  APPWORLD BENCHMARK COMPARISON REPORT",
        "=" * 70,
        "",
        "  TASK GOAL COMPLETION (TGC)",
        f"    Baseline:  {comparison['baseline_metrics']['tgc']:.1f}% ({comparison['baseline_metrics']['passed']}/{comparison['baseline_metrics']['total']})",
        f"    Enhanced:  {comparison['enhanced_metrics']['tgc']:.1f}% ({comparison['enhanced_metrics']['passed']}/{comparison['enhanced_metrics']['total']})",
        f"    Delta:     {comparison['comparison']['tgc_delta']:+.1f}%",
        "",
        "  SCENARIO GOAL COMPLETION (SGC)",
        f"    Baseline:  {comparison['baseline_sgc']['sgc']:.1f}% ({comparison['baseline_sgc']['passed_scenarios']}/{comparison['baseline_sgc']['total_scenarios']})",
        f"    Enhanced:  {comparison['enhanced_sgc']['sgc']:.1f}% ({comparison['enhanced_sgc']['passed_scenarios']}/{comparison['enhanced_sgc']['total_scenarios']})",
        f"    Delta:     {comparison['comparison']['sgc_delta']:+.1f}%",
        "",
        "  CONFUSION MATRIX",
        f"    Both pass:  {cm['both_pass']['count']}",
        f"    Improved:   {cm['improved']['count']}",
        f"    Regressed:  {cm['regressed']['count']}",
        f"    Both fail:  {cm['both_fail']['count']}",
        "",
        f"  NET IMPROVEMENT: {comparison['comparison']['net_improvement']:+d} tasks",
        "",
        "  STATISTICAL SIGNIFICANCE",
        f"    Test:       {stat.test_name}",
        f"    Statistic:  {stat.statistic}",
        f"    p-value:    {stat.p_value}",
        f"    Significant (p<0.05): {'Yes' if stat.significant else 'No'}",
        f"    Effect size (OR):     {stat.effect_size}",
        "",
        "  EFFICIENCY (tasks both solved)",
        f"    Baseline avg steps: {comparison['efficiency']['baseline_avg_steps']}",
        f"    Enhanced avg steps: {comparison['efficiency']['enhanced_avg_steps']}",
        "=" * 70,
    ]

    # Add improved/regressed task lists if not too long
    improved_ids = comparison["comparison"]["improved"]
    regressed_ids = comparison["comparison"]["regressed"]
    if improved_ids:
        lines.extend(["", "  IMPROVED TASKS:"])
        lines.extend(f"    + {tid}" for tid in improved_ids[:20])
        if len(improved_ids) > 20:
            lines.append(f"    ... and {len(improved_ids) - 20} more")
    if regressed_ids:
        lines.extend(["", "  REGRESSED TASKS:"])
        lines.extend(f"    - {tid}" for tid in regressed_ids[:20])
        if len(regressed_ids) > 20:
            lines.append(f"    ... and {len(regressed_ids) - 20} more")

    lines.append("")
    return "\n".join(lines)
