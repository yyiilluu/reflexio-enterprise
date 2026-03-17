"""
Aggregate evaluation results and produce per-question-type accuracy metrics.

Reads scored JSONL from 03_evaluate.py and prints a summary table.
Optionally compares multiple hypothesis files.

Usage:
    python 04_report.py --eval-file output/eval_results/oracle_profile_eval.jsonl
    python 04_report.py --eval-file output/eval_results/oracle_profile_eval.jsonl output/eval_results/oracle_interaction_eval.jsonl
"""

import argparse
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# LongMemEval question types
QUESTION_TYPES = [
    "information_extraction",
    "multi_session_reasoning",
    "knowledge_update",
    "temporal_reasoning",
    "abstention",
]


def load_eval_results(path: Path) -> list[dict]:
    """
    Load evaluation results from a scored JSONL file.

    Args:
        path (Path): Path to the eval JSONL file

    Returns:
        list[dict]: List of result dicts with autoeval_label
    """
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def compute_metrics(results: list[dict]) -> dict:
    """
    Compute per-type and overall accuracy metrics.

    Args:
        results (list[dict]): Evaluation results with question_type and autoeval_label

    Returns:
        dict: Metrics including per_type, macro_avg, overall, and abstention accuracy
    """
    type_counts: dict[str, Counter] = defaultdict(Counter)

    for r in results:
        qtype = r.get("question_type", "unknown")
        label = r.get("autoeval_label", "incorrect")
        type_counts[qtype][label] += 1

    per_type = {}
    for qtype in QUESTION_TYPES:
        counts = type_counts.get(qtype, Counter())
        total = counts["correct"] + counts["incorrect"]
        accuracy = counts["correct"] / total if total else 0.0
        per_type[qtype] = {
            "correct": counts["correct"],
            "total": total,
            "accuracy": accuracy,
        }

    # Macro average across types that have data
    type_accuracies = [m["accuracy"] for m in per_type.values() if m["total"] > 0]
    macro_avg = sum(type_accuracies) / len(type_accuracies) if type_accuracies else 0.0

    # Overall accuracy
    total_correct = sum(m["correct"] for m in per_type.values())
    total_all = sum(m["total"] for m in per_type.values())
    overall = total_correct / total_all if total_all else 0.0

    return {
        "per_type": per_type,
        "macro_avg": macro_avg,
        "overall": overall,
        "total_questions": total_all,
        "total_correct": total_correct,
    }


def print_report(name: str, metrics: dict) -> None:
    """
    Print a formatted report table.

    Args:
        name (str): Name/label for this result set
        metrics (dict): Output from compute_metrics()
    """
    print(f"\n{'=' * 60}")
    print(f" Results: {name}")
    print(f"{'=' * 60}")
    print(f"{'Question Type':<30} {'Correct':>8} {'Total':>8} {'Accuracy':>10}")
    print(f"{'-' * 30} {'-' * 8} {'-' * 8} {'-' * 10}")

    for qtype in QUESTION_TYPES:
        m = metrics["per_type"].get(qtype, {"correct": 0, "total": 0, "accuracy": 0.0})
        if m["total"] > 0:
            print(
                f"{qtype:<30} {m['correct']:>8} {m['total']:>8} {m['accuracy']:>9.1%}"
            )
        else:
            print(f"{qtype:<30} {'—':>8} {'—':>8} {'—':>10}")

    print(f"{'-' * 30} {'-' * 8} {'-' * 8} {'-' * 10}")
    print(
        f"{'Overall':<30} {metrics['total_correct']:>8} {metrics['total_questions']:>8} {metrics['overall']:>9.1%}"
    )
    print(f"{'Macro Average':<30} {'':>8} {'':>8} {metrics['macro_avg']:>9.1%}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate LongMemEval evaluation metrics"
    )
    parser.add_argument(
        "--eval-file",
        required=True,
        nargs="+",
        type=Path,
        help="One or more scored eval JSONL files",
    )
    parser.add_argument(
        "--output-json", type=Path, default=None, help="Save metrics as JSON"
    )
    args = parser.parse_args()

    all_metrics = {}
    for eval_file in args.eval_file:
        if not eval_file.exists():
            logger.warning("File not found: %s", eval_file)
            continue

        results = load_eval_results(eval_file)
        metrics = compute_metrics(results)
        name = eval_file.stem
        all_metrics[name] = metrics
        print_report(name, metrics)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(all_metrics, indent=2))
        logger.info("Metrics saved to %s", args.output_json)

    # Comparison table if multiple files
    if len(all_metrics) > 1:
        print(f"\n{'=' * 80}")
        print(" Comparison")
        print(f"{'=' * 80}")
        header = f"{'Question Type':<30}"
        for name in all_metrics:
            header += f" {name[:15]:>15}"
        print(header)
        print("-" * len(header))

        for qtype in QUESTION_TYPES:
            row = f"{qtype:<30}"
            for metrics in all_metrics.values():
                m = metrics["per_type"].get(qtype, {"accuracy": 0.0, "total": 0})
                row += f" {m['accuracy']:>14.1%}" if m["total"] > 0 else f" {'—':>15}"
            print(row)

        row = f"{'Overall':<30}"
        for metrics in all_metrics.values():
            row += f" {metrics['overall']:>14.1%}"
        print(row)

        row = f"{'Macro Avg':<30}"
        for metrics in all_metrics.values():
            row += f" {metrics['macro_avg']:>14.1%}"
        print(row)
        print()


if __name__ == "__main__":
    main()
