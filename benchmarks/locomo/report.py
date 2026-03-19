"""Results aggregation and output generation."""

from __future__ import annotations

import csv
import json
import logging
import math
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from benchmarks.locomo.config import CATEGORY_MAP

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from benchmarks.locomo.evaluate_qa import QAResult


# Type aliases
AggTable = dict[str, dict[str, float]]
PerSampleTable = dict[str, dict[int, dict[str, float]]]
AggResult = dict[str, Any]  # mixed types: AggTable and PerSampleTable values


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    mu = _mean(vals)
    return math.sqrt(sum((v - mu) ** 2 for v in vals) / (len(vals) - 1))


def _collect_scores(
    results: list[QAResult],
    score_attr: str = "score",
) -> dict[str, dict[str, list[float]]]:
    """
    Collect per-strategy per-category score lists.

    Args:
        results (list[QAResult]): All QA results
        score_attr (str): Attribute name on QAResult to collect

    Returns:
        dict: strategy -> category_name -> [scores]
    """
    scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        val = getattr(r, score_attr, None)
        if val is None:
            continue
        scores[r.strategy][r.category_name].append(val)
        # Exclude adversarial (cat 5) from overall — industry consensus
        if r.category != 5:
            scores[r.strategy]["overall"].append(val)
        scores[r.strategy]["overall_incl_adversarial"].append(val)
    return scores


def _collect_per_sample_scores(
    results: list[QAResult],
    score_attr: str = "score",
) -> dict[str, dict[int, dict[str, list[float]]]]:
    """
    Collect per-strategy per-sample per-category score lists.

    Args:
        results (list[QAResult]): All QA results
        score_attr (str): Attribute name on QAResult to collect

    Returns:
        dict: strategy -> sample_id -> category_name -> [scores]
    """
    scores: dict[str, dict[int, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for r in results:
        val = getattr(r, score_attr, None)
        if val is None:
            continue
        scores[r.strategy][r.sample_id][r.category_name].append(val)
        if r.category != 5:
            scores[r.strategy][r.sample_id]["overall"].append(val)
        scores[r.strategy][r.sample_id]["overall_incl_adversarial"].append(val)
    return scores


def aggregate(
    results: list[QAResult],
) -> AggResult:
    """
    Compute mean scores per strategy per category for both F1 and judge metrics.

    Args:
        results (list[QAResult]): All QA results

    Returns:
        dict with keys:
            "f1": strategy -> {category_name: mean_score, "overall": mean_score}
            "judge": strategy -> {category: mean} (empty if none)
            "f1_std": strategy -> {category: std_dev}
            "judge_std": strategy -> {category: std_dev}
            "f1_per_sample": strategy -> {sample_id: {category: mean}}
            "judge_per_sample": strategy -> {sample_id: {category: mean}}
    """
    f1_scores = _collect_scores(results, "score")
    judge_scores = _collect_scores(results, "judge_score")
    rr_scores = _collect_scores(results, "retrieval_recall_score")

    f1_per_sample = _collect_per_sample_scores(results, "score")
    judge_per_sample = _collect_per_sample_scores(results, "judge_score")

    def _agg_mean(raw: dict[str, dict[str, list[float]]]) -> AggTable:
        return {
            strategy: {cat: _mean(vals) for cat, vals in cats.items()}
            for strategy, cats in raw.items()
        }

    def _agg_std(raw: dict[str, dict[str, list[float]]]) -> AggTable:
        return {
            strategy: {cat: _std(vals) for cat, vals in cats.items()}
            for strategy, cats in raw.items()
        }

    def _agg_per_sample(
        raw: dict[str, dict[int, dict[str, list[float]]]],
    ) -> dict[str, dict[int, dict[str, float]]]:
        out: dict[str, dict[int, dict[str, float]]] = {}
        for strategy, samples in raw.items():
            out[strategy] = {}
            for sample_id, cats in samples.items():
                out[strategy][sample_id] = {
                    cat: _mean(vals) for cat, vals in cats.items()
                }
        return out

    return {
        "f1": _agg_mean(f1_scores),
        "judge": _agg_mean(judge_scores),
        "retrieval_recall": _agg_mean(rr_scores),
        "f1_std": _agg_std(f1_scores),
        "judge_std": _agg_std(judge_scores),
        "retrieval_recall_std": _agg_std(rr_scores),
        "f1_per_sample": _agg_per_sample(f1_per_sample),
        "judge_per_sample": _agg_per_sample(judge_per_sample),
    }


def _render_table(
    agg_mean: AggTable,
    agg_std: AggTable,
    title: str,
) -> str:
    """
    Render a single metric table as Markdown with mean +/- std.

    Args:
        agg_mean (AggTable): Mean scores per strategy per category
        agg_std (AggTable): Std dev scores per strategy per category
        title (str): Table title

    Returns:
        str: Markdown table
    """
    categories = [CATEGORY_MAP[i] for i in sorted(CATEGORY_MAP)] + ["overall"]
    lines = [f"### {title}", ""]
    header = "| Strategy | " + " | ".join(c.title() for c in categories) + " |"
    separator = "|" + "|".join(["---"] * (len(categories) + 1)) + "|"
    lines.extend([header, separator])

    for strategy in sorted(agg_mean):
        cells = [strategy]
        for cat in categories:
            mean = agg_mean[strategy].get(cat, 0.0)
            std = agg_std.get(strategy, {}).get(cat, 0.0)
            if std > 0:
                cells.append(f"{mean:.3f} +/- {std:.3f}")
            else:
                cells.append(f"{mean:.3f}")
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def _render_per_sample_table(
    per_sample: PerSampleTable,
    title: str,
) -> str:
    """
    Render per-conversation breakdown as Markdown.

    Args:
        per_sample: strategy -> sample_id -> category_name -> mean_score
        title (str): Section title

    Returns:
        str: Markdown section
    """
    categories = [CATEGORY_MAP[i] for i in sorted(CATEGORY_MAP)] + ["overall"]
    lines = [f"### {title}", ""]

    for strategy in sorted(per_sample):
        lines.append(f"**{strategy}**\n")
        header = "| Sample | " + " | ".join(c.title() for c in categories) + " |"
        separator = "|" + "|".join(["---"] * (len(categories) + 1)) + "|"
        lines.extend([header, separator])

        for sample_id in sorted(per_sample[strategy]):
            cells = [str(sample_id)]
            for cat in categories:
                score = per_sample[strategy][sample_id].get(cat, 0.0)
                cells.append(f"{score:.3f}")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    return "\n".join(lines)


def to_markdown(agg: AggResult) -> str:
    """
    Render aggregated results as Markdown with F1 and Judge tables.

    Args:
        agg: Output of aggregate()

    Returns:
        str: Full markdown report
    """
    sections = [_render_table(agg["f1"], agg["f1_std"], "Token F1 Scores")]

    if agg["judge"]:
        sections.append(
            _render_table(agg["judge"], agg["judge_std"], "LLM Judge Scores")
        )

    if agg.get("retrieval_recall"):
        sections.append(
            _render_table(
                agg["retrieval_recall"],
                agg.get("retrieval_recall_std", {}),
                "Retrieval Recall",
            )
        )

    # Per-conversation breakdown
    if agg["f1_per_sample"]:
        sections.append(
            _render_per_sample_table(agg["f1_per_sample"], "Per-Conversation F1 Scores")
        )

    if agg["judge_per_sample"]:
        sections.append(
            _render_per_sample_table(
                agg["judge_per_sample"], "Per-Conversation Judge Scores"
            )
        )

    return "\n\n".join(sections)


def to_csv(agg: AggResult) -> str:
    """
    Render aggregated F1 results as CSV.

    Args:
        agg: Output of aggregate()

    Returns:
        str: CSV string
    """
    categories = [CATEGORY_MAP[i] for i in sorted(CATEGORY_MAP)] + ["overall"]
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["strategy", "metric"] + [c.title() for c in categories])

    for metric_key, label in [
        ("f1", "f1"),
        ("judge", "judge"),
        ("retrieval_recall", "retrieval_recall"),
    ]:
        table = agg[metric_key]
        for strategy in sorted(table):
            row = [strategy, label] + [
                f"{table[strategy].get(cat, 0.0):.4f}" for cat in categories
            ]
            writer.writerow(row)

    return output.getvalue()


def to_json(results: list[QAResult], agg: AggResult) -> str:
    """
    Render full results + aggregated summary as JSON.

    Args:
        results (list[QAResult]): All individual results
        agg: Output of aggregate()

    Returns:
        str: JSON string
    """

    # Convert per_sample int keys to strings for JSON
    def _stringify_keys(d: Any) -> dict[str, dict[str, dict[str, float]]]:
        return {
            strategy: {str(sid): cats for sid, cats in samples.items()}
            for strategy, samples in d.items()
        }

    data = {
        "summary": {
            "f1": agg["f1"],
            "judge": agg["judge"],
            "retrieval_recall": agg.get("retrieval_recall", {}),
            "f1_std": agg["f1_std"],
            "judge_std": agg["judge_std"],
            "retrieval_recall_std": agg.get("retrieval_recall_std", {}),
        },
        "per_sample": {
            "f1": _stringify_keys(agg["f1_per_sample"]),
            "judge": _stringify_keys(agg["judge_per_sample"]),
        },
        "results": [r.to_dict() for r in results],
    }
    return json.dumps(data, indent=2)


def save_report(
    results: list[QAResult],
    output_dir: str | Path,
) -> None:
    """
    Generate and save all report formats.

    Args:
        results (list[QAResult]): All evaluation results
        output_dir (str | Path): Output directory
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    agg = aggregate(results)

    # Markdown
    md = to_markdown(agg)
    (output_dir / "report.md").write_text(md)
    logger.info("\n%s", md)

    # CSV
    csv_str = to_csv(agg)
    (output_dir / "report.csv").write_text(csv_str)

    # JSON (full results + summary)
    json_str = to_json(results, agg)
    (output_dir / "report.json").write_text(json_str)

    logger.info("Reports saved to %s/", output_dir)


def save_multi_run_report(
    all_run_aggs: list[AggResult],
    output_dir: str | Path,
) -> None:
    """
    Aggregate results across multiple runs and save a combined report.

    For each (strategy, category) cell, computes mean +/- std across runs.

    Args:
        all_run_aggs (list[dict[str, AggTable]]): List of aggregate outputs, one per run
        output_dir (str | Path): Output directory for the combined report
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect per-cell values across runs for f1 and judge
    def _aggregate_across_runs(metric_key: str) -> tuple[AggTable, AggTable]:
        """Returns (mean_table, std_table) across runs for a given metric."""
        cell_values: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for agg in all_run_aggs:
            table = agg.get(metric_key, {})
            for strategy, cats in table.items():
                for cat, val in cats.items():
                    cell_values[strategy][cat].append(val)

        mean_table: AggTable = {}
        std_table: AggTable = {}
        for strategy, cats in cell_values.items():
            mean_table[strategy] = {cat: _mean(vals) for cat, vals in cats.items()}
            std_table[strategy] = {cat: _std(vals) for cat, vals in cats.items()}
        return mean_table, std_table

    f1_mean, f1_std = _aggregate_across_runs("f1")
    judge_mean, judge_std = _aggregate_across_runs("judge")

    # Markdown
    num_runs = len(all_run_aggs)
    md_parts = [f"# Multi-Run Report ({num_runs} runs)\n"]
    md_parts.append(
        _render_table(
            f1_mean, f1_std, f"Token F1 Scores (mean +/- std, {num_runs} runs)"
        )
    )
    if judge_mean:
        md_parts.append(
            _render_table(
                judge_mean,
                judge_std,
                f"LLM Judge Scores (mean +/- std, {num_runs} runs)",
            )
        )
    md = "\n\n".join(md_parts)
    (output_dir / "report.md").write_text(md)
    logger.info("\n%s", md)

    # JSON
    data = {
        "num_runs": num_runs,
        "summary": {
            "f1": f1_mean,
            "judge": judge_mean,
            "f1_std": f1_std,
            "judge_std": judge_std,
        },
    }
    (output_dir / "report.json").write_text(json.dumps(data, indent=2))

    logger.info("Multi-run reports saved to %s/", output_dir)
