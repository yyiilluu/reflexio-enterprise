#!/usr/bin/env python3
"""
Script to print labels from customer_support.jsonl grouped by type.
"""

import json
from collections import defaultdict
from pathlib import Path


def load_and_group_labels(file_path: str) -> dict[str, list[dict]]:
    """
    Load JSONL file and group labels by their type.

    Args:
        file_path: Path to the JSONL file

    Returns:
        Dictionary mapping label type to list of labels with their turn info
    """
    labels_by_type = defaultdict(list)

    with open(file_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            entry = json.loads(line)
            turn = entry.get("turn")
            role = entry.get("role")
            content = entry.get("content", "")

            for label in entry.get("labels", []):
                label_type = label.get("type")
                label_content = label.get("content")

                labels_by_type[label_type].append(
                    {
                        "turn": turn,
                        "role": role,
                        "message": content[:80] + "..."
                        if len(content) > 80
                        else content,
                        "label": label_content,
                    }
                )

    return dict(labels_by_type)


def print_labels_by_type(labels_by_type: dict[str, list[dict]]) -> None:
    """
    Print labels grouped by type in a readable format.

    Args:
        labels_by_type: Dictionary mapping label type to list of labels
    """
    for label_type, labels in sorted(labels_by_type.items()):
        print(f"\n{'=' * 80}")
        print(f"TYPE: {label_type.upper()} ({len(labels)} labels)")
        print("=" * 80)

        for i, label_info in enumerate(labels, 1):
            print(f"\n[{i}] Turn {label_info['turn']} ({label_info['role']})")
            print(f'    Message: "{label_info["message"]}"')
            print(f"    Label:   {label_info['label']}")


def main():
    script_dir = Path(__file__).parent
    file_path = script_dir / "customer_support.jsonl"

    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        return

    labels_by_type = load_and_group_labels(str(file_path))

    if not labels_by_type:
        print("No labels found in the file.")
        return

    # Print summary
    print("LABEL SUMMARY")
    print("-" * 40)
    for label_type, labels in sorted(labels_by_type.items()):
        print(f"  {label_type}: {len(labels)} labels")

    # Print detailed labels by type
    print_labels_by_type(labels_by_type)


if __name__ == "__main__":
    main()
