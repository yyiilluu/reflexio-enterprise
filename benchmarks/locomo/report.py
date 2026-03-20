"""Results aggregation and output generation."""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

from benchmarks.locomo.config import CATEGORY_MAP

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from benchmarks.locomo.evaluate_qa import QAResult


def aggregate(results: list[QAResult]) -> dict[str, dict[str, float]]:
    """
    Compute mean scores per strategy per category.

    Args:
        results (list[QAResult]): All QA results

    Returns:
        dict[str, dict[str, float]]: strategy -> {category_name: mean_score, "overall": mean_score}
    """
    # Collect scores: strategy -> category_name -> [scores]
    scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        scores[r.strategy][r.category_name].append(r.score)
        scores[r.strategy]["overall"].append(r.score)

    # Compute means
    aggregated: dict[str, dict[str, float]] = {}
    for strategy, cats in scores.items():
        aggregated[strategy] = {}
        for cat, vals in cats.items():
            aggregated[strategy][cat] = sum(vals) / len(vals) if vals else 0.0

    return aggregated


def to_markdown(aggregated: dict[str, dict[str, float]]) -> str:
    """
    Render aggregated results as a Markdown table.

    Args:
        aggregated: Output of aggregate()

    Returns:
        str: Markdown table
    """
    categories = [CATEGORY_MAP[i] for i in sorted(CATEGORY_MAP)] + ["overall"]
    header = "| Strategy | " + " | ".join(c.title() for c in categories) + " |"
    separator = "|" + "|".join(["---"] * (len(categories) + 1)) + "|"

    rows = [header, separator]
    for strategy in sorted(aggregated):
        cells = [strategy]
        for cat in categories:
            score = aggregated[strategy].get(cat, 0.0)
            cells.append(f"{score:.3f}")
        rows.append("| " + " | ".join(cells) + " |")

    return "\n".join(rows)


def to_csv(aggregated: dict[str, dict[str, float]]) -> str:
    """
    Render aggregated results as CSV.

    Args:
        aggregated: Output of aggregate()

    Returns:
        str: CSV string
    """
    categories = [CATEGORY_MAP[i] for i in sorted(CATEGORY_MAP)] + ["overall"]
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["strategy"] + [c.title() for c in categories])
    for strategy in sorted(aggregated):
        row = [strategy] + [
            f"{aggregated[strategy].get(cat, 0.0):.4f}" for cat in categories
        ]
        writer.writerow(row)
    return output.getvalue()


def to_json(results: list[QAResult], aggregated: dict[str, dict[str, float]]) -> str:
    """
    Render full results + aggregated summary as JSON.

    Args:
        results (list[QAResult]): All individual results
        aggregated: Output of aggregate()

    Returns:
        str: JSON string
    """
    data = {
        "summary": aggregated,
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

    aggregated = aggregate(results)

    # Markdown
    md = to_markdown(aggregated)
    (output_dir / "report.md").write_text(md)
    logger.info("\n%s", md)

    # CSV
    csv_str = to_csv(aggregated)
    (output_dir / "report.csv").write_text(csv_str)

    # JSON (full results + summary)
    json_str = to_json(results, aggregated)
    (output_dir / "report.json").write_text(json_str)

    logger.info("Reports saved to %s/", output_dir)
