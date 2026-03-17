"""
Run LongMemEval LLM-as-judge evaluation on generated hypotheses.

Calls LongMemEval's evaluate_qa.py with the hypothesis JSONL and reference data.
Uses GPT-4o as the judge model (per LongMemEval standard, >97% human agreement).

Usage:
    python 03_evaluate.py --hypothesis output/hypotheses/oracle_profile.jsonl --reference data/longmemeval_oracle.json
    python 03_evaluate.py --hypothesis output/hypotheses/oracle_profile.jsonl --reference data/longmemeval_oracle.json --judge-model gpt-4o
"""

import argparse
import json
import logging
from pathlib import Path

import litellm
from config import DEFAULT_JUDGE_MODEL, EVAL_RESULTS_DIR
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

JUDGE_SYSTEM_PROMPT = """\
You are an impartial judge evaluating the quality of an AI assistant's answer to a question about a user.

You will be given:
1. A question about the user
2. The ground truth answer (reference)
3. The AI assistant's answer (hypothesis)

Your task is to determine if the hypothesis is correct by comparing it to the reference answer.

Rules:
- The hypothesis is CORRECT if it conveys the same essential information as the reference, even if worded differently.
- The hypothesis is CORRECT if it contains the reference answer plus additional correct details.
- The hypothesis is INCORRECT if it contradicts the reference answer or provides wrong information.
- The hypothesis is INCORRECT if the question requires a specific answer but the hypothesis says "I don't know" or equivalent.
- The hypothesis is CORRECT if both the reference and hypothesis indicate the information is unknown/unavailable.
- For numerical answers, minor rounding differences are acceptable.
- For list-type answers, the hypothesis should contain all key items from the reference.

Respond with ONLY one word: "correct" or "incorrect".
"""


def judge_single(
    question: str,
    reference: str,
    hypothesis: str,
    model: str,
) -> str:
    """
    Use LLM-as-judge to evaluate a single hypothesis against the reference.

    Args:
        question (str): The original question
        reference (str): Ground truth answer
        hypothesis (str): Generated answer to evaluate
        model (str): Judge model identifier

    Returns:
        str: "correct" or "incorrect"
    """
    user_msg = (
        f"Question: {question}\n\n"
        f"Reference answer: {reference}\n\n"
        f"AI assistant's answer: {hypothesis}"
    )

    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    resp = litellm.completion(model=model, messages=messages, temperature=0.0)
    verdict = resp.choices[0].message.content.strip().lower()

    # Normalize to "correct" or "incorrect"
    if "correct" in verdict and "incorrect" not in verdict:
        return "correct"
    return "incorrect"


def load_hypotheses(path: Path) -> dict[str, str]:
    """
    Load hypothesis JSONL into a dict keyed by question_id.

    Args:
        path (Path): Path to the JSONL file

    Returns:
        dict[str, str]: Mapping of question_id → hypothesis
    """
    hypotheses = {}
    with path.open() as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                hypotheses[str(record["question_id"])] = record["hypothesis"]
    return hypotheses


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate LongMemEval hypotheses with LLM-as-judge"
    )
    parser.add_argument(
        "--hypothesis", required=True, type=Path, help="Path to hypothesis JSONL"
    )
    parser.add_argument(
        "--reference", required=True, type=Path, help="Path to reference JSON"
    )
    parser.add_argument(
        "--judge-model", default=DEFAULT_JUDGE_MODEL, help="Judge model"
    )
    parser.add_argument("--output", type=Path, default=None, help="Output JSONL path")
    parser.add_argument("--start-idx", type=int, default=0, help="Start question index")
    parser.add_argument("--end-idx", type=int, default=None, help="End question index")
    args = parser.parse_args()

    if not args.hypothesis.exists():
        logger.error("Hypothesis file not found: %s", args.hypothesis)
        return
    if not args.reference.exists():
        logger.error("Reference file not found: %s", args.reference)
        return

    hypotheses = load_hypotheses(args.hypothesis)
    reference_data = json.loads(args.reference.read_text())
    questions = reference_data[args.start_idx : args.end_idx]

    output_path = args.output or (
        EVAL_RESULTS_DIR / f"{args.hypothesis.stem}_eval.jsonl"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Evaluating %d questions with %s (hypotheses: %d)",
        len(questions),
        args.judge_model,
        len(hypotheses),
    )

    correct, total = 0, 0
    with output_path.open("a") as f:
        for question in questions:
            qid = str(question["question_id"])
            if qid not in hypotheses:
                logger.warning("No hypothesis for question %s, skipping", qid)
                continue

            try:
                verdict = judge_single(
                    question=question["question"],
                    reference=question["answer"],
                    hypothesis=hypotheses[qid],
                    model=args.judge_model,
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
        "Evaluation complete. Accuracy: %d/%d = %.1f%%", correct, total, accuracy * 100
    )
    logger.info("Results written to %s", output_path)


if __name__ == "__main__":
    main()
