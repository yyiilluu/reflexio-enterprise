"""
Download LongMemEval data from HuggingFace and evaluation scripts from GitHub.

Usage:
    python download_data.py
"""

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from config import DATA_DIR, EVAL_SCRIPTS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HF_DATASET = "xiaowu0162/longmemeval-cleaned"
GITHUB_REPO = "https://github.com/xiaowu0162/LongMemEval.git"

# Files we want from the HuggingFace dataset
DATASET_FILES = {
    "longmemeval_oracle.json": "oracle",
    "longmemeval_s_cleaned.json": "s_cleaned",
    "longmemeval_m_cleaned.json": "m_cleaned",
}


def download_hf_data() -> None:
    """Download LongMemEval dataset files from HuggingFace using the datasets library."""
    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("Install datasets: pip install datasets")
        raise

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Loading dataset from HuggingFace: %s", HF_DATASET)
    dataset = load_dataset(HF_DATASET)

    for split_name in dataset:
        output_file = DATA_DIR / f"longmemeval_{split_name}.json"
        if output_file.exists():
            logger.info("Skipping %s (already exists)", output_file.name)
            continue

        logger.info("Saving split '%s' → %s", split_name, output_file.name)
        records = [dict(row) for row in dataset[split_name]]
        output_file.write_text(json.dumps(records, indent=2, ensure_ascii=False))
        logger.info("  Saved %d records", len(records))


def download_eval_scripts() -> None:
    """Clone LongMemEval repo and extract evaluation scripts."""
    EVAL_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    target_files = ["evaluate_qa.py", "print_qa_metrics.py"]
    if all((EVAL_SCRIPTS_DIR / f).exists() for f in target_files):
        logger.info("Eval scripts already present, skipping clone")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        logger.info("Cloning LongMemEval repo (sparse checkout)...")
        subprocess.run(  # noqa: S603
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                GITHUB_REPO,
                tmpdir,
            ],  # noqa: S607
            check=True,
            capture_output=True,
        )
        subprocess.run(  # noqa: S603
            ["git", "-C", tmpdir, "sparse-checkout", "set", "src/evaluation"],  # noqa: S607
            check=True,
            capture_output=True,
        )

        eval_src = Path(tmpdir) / "src" / "evaluation"
        for fname in target_files:
            src = eval_src / fname
            dst = EVAL_SCRIPTS_DIR / fname
            if src.exists():
                dst.write_text(src.read_text())
                logger.info("Copied %s", fname)
            else:
                logger.warning("Expected file not found: %s", src)


def main() -> None:
    download_hf_data()
    download_eval_scripts()
    logger.info("Done. Data in %s, eval scripts in %s", DATA_DIR, EVAL_SCRIPTS_DIR)


if __name__ == "__main__":
    main()
