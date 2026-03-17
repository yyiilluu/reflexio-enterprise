"""
Run the full LongMemEval benchmark pipeline end-to-end.

Steps executed in order:
  1. Download data from HuggingFace + eval scripts from GitHub
  2. Ingest conversation sessions into Reflexio
  3. Retrieve memories and generate answers
  4. Evaluate answers with LLM-as-judge
  5. Report per-type accuracy metrics

Usage:
    python run_all.py \\
        --reflexio-api-key KEY \\
        --reflexio-url http://localhost:8081 \\
        --variant oracle \\
        --retrieval-mode profile \\
        --answer-model minimax/MiniMax-M2.5 \\
        --judge-model gpt-4o \\
        --end-idx 10

    # Skip steps that already completed
    python run_all.py --variant oracle --retrieval-mode profile --skip-download --skip-ingest
"""

import argparse
import importlib
import json
import logging
import os
import sys
from pathlib import Path

from config import (
    DATA_DIR,
    DEFAULT_ANSWER_MODEL,
    DEFAULT_JUDGE_MODEL,
    EVAL_RESULTS_DIR,
    HYPOTHESES_DIR,
    REFLEXIO_URL,
    make_reflexio_config,
)
from dotenv import load_dotenv
from download_data import download_eval_scripts, download_hf_data

from reflexio.reflexio_client.reflexio import ReflexioClient

# Modules with digit-prefixed names need importlib
_ingest = importlib.import_module("01_ingest")
_retrieve = importlib.import_module("02_retrieve_and_answer")
_evaluate = importlib.import_module("03_evaluate")

_report = importlib.import_module("04_report")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the full benchmark pipeline."""
    parser = argparse.ArgumentParser(
        description="Run the full LongMemEval benchmark pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Connection
    parser.add_argument(
        "--reflexio-api-key",
        default=os.environ.get("REFLEXIO_API_KEY"),
        help="Reflexio API key (default: $REFLEXIO_API_KEY env var)",
    )
    parser.add_argument(
        "--reflexio-url",
        default=REFLEXIO_URL,
        help=f"Reflexio backend URL (default: {REFLEXIO_URL})",
    )

    # Dataset
    parser.add_argument(
        "--variant",
        default="oracle",
        help="Dataset variant: oracle / s / m (default: oracle)",
    )
    parser.add_argument(
        "--data-file", type=Path, default=None, help="Override data file path"
    )

    # Retrieval & answer
    parser.add_argument(
        "--retrieval-mode",
        default="profile",
        choices=["profile", "interaction", "both"],
        help="Retrieval mode (default: profile)",
    )
    parser.add_argument(
        "--answer-model",
        default=DEFAULT_ANSWER_MODEL,
        help=f"LLM for answers (default: {DEFAULT_ANSWER_MODEL})",
    )
    parser.add_argument(
        "--top-k", type=int, default=20, help="Max retrieval results (default: 20)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.3,
        help="Similarity threshold for profiles (default: 0.3)",
    )

    # Evaluation
    parser.add_argument(
        "--judge-model",
        default=DEFAULT_JUDGE_MODEL,
        help=f"LLM judge model (default: {DEFAULT_JUDGE_MODEL})",
    )

    # Subset selection
    parser.add_argument(
        "--start-idx", type=int, default=0, help="Start question index (inclusive)"
    )
    parser.add_argument(
        "--end-idx", type=int, default=None, help="End question index (exclusive)"
    )

    # Ingestion pacing
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="Seconds between ingestion publishes (default: 1.0)",
    )

    # Skip flags
    parser.add_argument(
        "--skip-download", action="store_true", help="Skip step 1: download data"
    )
    parser.add_argument(
        "--skip-ingest", action="store_true", help="Skip step 2: ingest into Reflexio"
    )
    parser.add_argument(
        "--skip-retrieve", action="store_true", help="Skip step 3: retrieve & answer"
    )
    parser.add_argument(
        "--skip-evaluate", action="store_true", help="Skip step 4: evaluate answers"
    )
    parser.add_argument(
        "--skip-report", action="store_true", help="Skip step 5: print report"
    )

    return parser.parse_args()


def step_download() -> None:
    """Step 1: Download LongMemEval data and eval scripts."""
    logger.info("=" * 60)
    logger.info("STEP 1: Download data")
    logger.info("=" * 60)
    download_hf_data()
    download_eval_scripts()


def step_ingest(
    client: ReflexioClient,
    variant: str,
    data: list[dict],
    sleep_between: float,
) -> None:
    """
    Step 2: Ingest conversation sessions into Reflexio.

    Args:
        client (ReflexioClient): Configured Reflexio client
        variant (str): Dataset variant
        data (list[dict]): Questions to ingest
        sleep_between (float): Seconds between publish calls
    """
    logger.info("=" * 60)
    logger.info("STEP 2: Ingest (%d questions)", len(data))
    logger.info("=" * 60)

    # Set Reflexio config for LongMemEval extraction
    config = make_reflexio_config()
    logger.info("Setting Reflexio config for LongMemEval...")
    client.set_config(config)

    ingested, skipped = 0, 0
    for question in data:
        qid = str(question["question_id"])
        if _ingest.is_ingested(variant, qid):
            logger.info("Skipping question %s (already ingested)", qid)
            skipped += 1
            continue
        try:
            _ingest.ingest_question(
                client, variant, question, sleep_between=sleep_between
            )
            ingested += 1
        except Exception:
            logger.exception("Error ingesting question %s", qid)

    logger.info("Ingest done. Ingested: %d, Skipped: %d", ingested, skipped)


def step_retrieve_and_answer(
    client: ReflexioClient,
    variant: str,
    data: list[dict],
    retrieval_mode: str,
    answer_model: str,
    top_k: int,
    threshold: float,
    hypothesis_path: Path,
) -> None:
    """
    Step 3: Retrieve memories and generate answers.

    Args:
        client (ReflexioClient): Configured Reflexio client
        variant (str): Dataset variant
        data (list[dict]): Questions to process
        retrieval_mode (str): Retrieval mode (profile / interaction / both)
        answer_model (str): LLM model for answer generation
        top_k (int): Max retrieval results
        threshold (float): Similarity threshold
        hypothesis_path (Path): Output JSONL path
    """
    logger.info("=" * 60)
    logger.info(
        "STEP 3: Retrieve & Answer (%d questions, mode=%s, model=%s)",
        len(data),
        retrieval_mode,
        answer_model,
    )
    logger.info("=" * 60)

    hypothesis_path.parent.mkdir(parents=True, exist_ok=True)

    with hypothesis_path.open("a") as f:
        for question in data:
            try:
                result = _retrieve.process_question(
                    client,
                    variant,
                    question,
                    retrieval_mode,
                    answer_model,
                    top_k,
                    threshold,
                )
                f.write(json.dumps(result) + "\n")
                f.flush()
            except Exception:  # noqa: PERF203
                logger.exception(
                    "Error processing question %s", question.get("question_id")
                )

    logger.info("Hypotheses written to %s", hypothesis_path)


def step_evaluate(
    data: list[dict],
    hypothesis_path: Path,
    judge_model: str,
    eval_path: Path,
) -> None:
    """
    Step 4: Evaluate answers with LLM-as-judge.

    Args:
        data (list[dict]): Reference questions
        hypothesis_path (Path): Path to hypothesis JSONL
        judge_model (str): Judge model identifier
        eval_path (Path): Output eval JSONL path
    """
    logger.info("=" * 60)
    logger.info("STEP 4: Evaluate (judge=%s)", judge_model)
    logger.info("=" * 60)

    if not hypothesis_path.exists():
        logger.error(
            "Hypothesis file not found: %s — skipping evaluation", hypothesis_path
        )
        return

    hypotheses = _evaluate.load_hypotheses(hypothesis_path)
    eval_path.parent.mkdir(parents=True, exist_ok=True)

    correct, total = 0, 0
    with eval_path.open("a") as f:
        for question in data:
            qid = str(question["question_id"])
            if qid not in hypotheses:
                logger.warning("No hypothesis for question %s, skipping", qid)
                continue

            try:
                verdict = _evaluate.judge_single(
                    question=question["question"],
                    reference=question["answer"],
                    hypothesis=hypotheses[qid],
                    model=judge_model,
                )
                total += 1
                if verdict == "correct":
                    correct += 1

                result = {
                    "question_id": qid,
                    "question_type": question.get("question_type", "unknown"),
                    "question": question["question"],
                    "reference": question["answer"],
                    "hypothesis": hypotheses[qid],
                    "autoeval_label": verdict,
                }
                f.write(json.dumps(result) + "\n")
                f.flush()

                logger.info(
                    "  Q%s [%s]: %s", qid, question.get("question_type", "?"), verdict
                )
            except Exception:
                logger.exception("Error evaluating question %s", qid)

    accuracy = correct / total if total else 0.0
    logger.info(
        "Evaluation done. Accuracy: %d/%d = %.1f%%", correct, total, accuracy * 100
    )
    logger.info("Results written to %s", eval_path)


def step_report(eval_path: Path) -> None:
    """
    Step 5: Load eval results and print metrics report.

    Args:
        eval_path (Path): Path to eval JSONL file
    """
    logger.info("=" * 60)
    logger.info("STEP 5: Report")
    logger.info("=" * 60)

    if not eval_path.exists():
        logger.error("Eval file not found: %s — skipping report", eval_path)
        return

    results = _report.load_eval_results(eval_path)
    metrics = _report.compute_metrics(results)
    _report.print_report(eval_path.stem, metrics)


def main() -> None:
    args = parse_args()

    # Derive paths
    data_file = args.data_file or (DATA_DIR / f"longmemeval_{args.variant}.json")
    hypothesis_path = HYPOTHESES_DIR / f"{args.variant}_{args.retrieval_mode}.jsonl"
    eval_path = EVAL_RESULTS_DIR / f"{args.variant}_{args.retrieval_mode}_eval.jsonl"

    # --- Step 1: Download ---
    if not args.skip_download:
        step_download()

    # Load data (needed for steps 2-4)
    needs_data = not (args.skip_ingest and args.skip_retrieve and args.skip_evaluate)
    data: list[dict] = []
    if needs_data:
        if not data_file.exists():
            logger.error("Data file not found: %s", data_file)
            logger.error("Run without --skip-download to fetch the data first.")
            sys.exit(1)
        all_data = json.loads(data_file.read_text())
        data = all_data[args.start_idx : args.end_idx]
        logger.info(
            "Loaded %d questions from %s [%d:%s]",
            len(data),
            data_file.name,
            args.start_idx,
            args.end_idx,
        )

    # Create client (needed for steps 2 & 3)
    client: ReflexioClient | None = None
    needs_client = not (args.skip_ingest and args.skip_retrieve)
    if needs_client:
        if not args.reflexio_api_key:
            logger.error(
                "Reflexio API key required. Pass --reflexio-api-key or set $REFLEXIO_API_KEY."
            )
            sys.exit(1)
        client = ReflexioClient(
            api_key=args.reflexio_api_key, url_endpoint=args.reflexio_url
        )
        logger.info("Connected to Reflexio at %s", args.reflexio_url)

    # --- Step 2: Ingest ---
    if not args.skip_ingest:
        # client is guaranteed non-None here by the needs_client check above
        step_ingest(client, args.variant, data, args.sleep)  # type: ignore[arg-type]

    # --- Step 3: Retrieve & Answer ---
    if not args.skip_retrieve:
        step_retrieve_and_answer(
            client,
            args.variant,
            data,  # type: ignore[arg-type]
            args.retrieval_mode,
            args.answer_model,
            args.top_k,
            args.threshold,
            hypothesis_path,
        )

    # --- Step 4: Evaluate ---
    if not args.skip_evaluate:
        step_evaluate(data, hypothesis_path, args.judge_model, eval_path)

    # --- Step 5: Report ---
    if not args.skip_report:
        step_report(eval_path)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
