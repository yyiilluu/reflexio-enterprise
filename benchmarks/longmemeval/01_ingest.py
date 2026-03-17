"""
Ingest LongMemEval conversation sessions into Reflexio.

For each question, creates a unique user_id and publishes all haystack sessions
as interactions. Uses checkpointing for resumable execution.

Usage:
    python 01_ingest.py --variant oracle --data-file data/longmemeval_oracle.json
    python 01_ingest.py --variant oracle --data-file data/longmemeval_oracle.json --start-idx 0 --end-idx 10
"""

import argparse
import json
import logging
import time
from pathlib import Path

from config import (
    INGEST_STATE_DIR,
    REFLEXIO_URL,
    make_reflexio_config,
    make_session_id,
    make_user_id,
    parse_longmemeval_date,
)
from dotenv import load_dotenv
from reflexio_commons.api_schema.service_schemas import InteractionData

from reflexio.reflexio_client.reflexio import ReflexioClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")


def checkpoint_path(variant: str, question_id: str) -> Path:
    """
    Return the checkpoint file path for a given question.

    Args:
        variant (str): Dataset variant
        question_id (str): Question identifier

    Returns:
        Path: Path to the .done checkpoint file
    """
    return INGEST_STATE_DIR / variant / f"{question_id}.done"


def is_ingested(variant: str, question_id: str) -> bool:
    """Check whether a question has already been fully ingested."""
    return checkpoint_path(variant, question_id).exists()


def mark_ingested(variant: str, question_id: str) -> None:
    """Write a checkpoint file indicating successful ingestion."""
    cp = checkpoint_path(variant, question_id)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text("done")


def build_interactions(session: dict) -> list[InteractionData]:
    """
    Convert a LongMemEval session dict to a list of InteractionData objects.

    Args:
        session (dict): A session from haystack_sessions containing 'conversation' and optionally 'date'

    Returns:
        list[InteractionData]: Interaction objects ready for publish_interaction()
    """
    interactions = []
    # Try to extract timestamp from session date
    timestamp = None
    if date_str := session.get("date"):
        try:
            timestamp = parse_longmemeval_date(date_str)
        except ValueError:
            logger.warning("Could not parse date: %s", date_str)

    for turn in session.get("conversation", []):
        role = turn.get("role", "user")
        content = turn.get("content", "")
        kwargs: dict = {"role": role, "content": content}
        if timestamp is not None:
            kwargs["created_at"] = timestamp
        interactions.append(InteractionData(**kwargs))

    return interactions


def ingest_question(
    client: ReflexioClient,
    variant: str,
    question: dict,
    sleep_between: float = 1.0,
) -> None:
    """
    Ingest all sessions for a single LongMemEval question.

    Args:
        client (ReflexioClient): The Reflexio client
        variant (str): Dataset variant
        question (dict): A single question dict from the dataset
        sleep_between (float): Seconds to sleep between publish calls
    """
    question_id = str(question["question_id"])
    user_id = make_user_id(variant, question_id)
    sessions = question.get("haystack_sessions", [])

    logger.info(
        "Ingesting question %s (user_id=%s, %d sessions)",
        question_id,
        user_id,
        len(sessions),
    )

    for idx, session in enumerate(sessions):
        session_id = make_session_id(question_id, idx)
        interactions = build_interactions(session)
        if not interactions:
            logger.warning("  Session %d has no interactions, skipping", idx)
            continue

        logger.info(
            "  Publishing session %d/%d (%d turns)",
            idx + 1,
            len(sessions),
            len(interactions),
        )
        resp = client.publish_interaction(
            user_id=user_id,
            interactions=interactions,
            session_id=session_id,
            wait_for_response=True,
        )
        if resp and not resp.success:
            logger.error("  Failed to publish session %d: %s", idx, resp.message)
        elif resp:
            logger.info("  Session %d published successfully", idx)

        if sleep_between > 0 and idx < len(sessions) - 1:
            time.sleep(sleep_between)

    mark_ingested(variant, question_id)
    logger.info("Question %s ingestion complete", question_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest LongMemEval sessions into Reflexio"
    )
    parser.add_argument(
        "--variant", required=True, help="Dataset variant (oracle, s, m)"
    )
    parser.add_argument(
        "--data-file", required=True, type=Path, help="Path to LongMemEval JSON file"
    )
    parser.add_argument(
        "--start-idx", type=int, default=0, help="Start question index (inclusive)"
    )
    parser.add_argument(
        "--end-idx", type=int, default=None, help="End question index (exclusive)"
    )
    parser.add_argument(
        "--sleep", type=float, default=1.0, help="Sleep seconds between publishes"
    )
    parser.add_argument(
        "--setup-config",
        action="store_true",
        help="Set Reflexio config before ingesting",
    )
    args = parser.parse_args()

    if not args.data_file.exists():
        logger.error("Data file not found: %s", args.data_file)
        return

    data = json.loads(args.data_file.read_text())
    logger.info("Loaded %d questions from %s", len(data), args.data_file)

    client = ReflexioClient(url_endpoint=REFLEXIO_URL)

    # Optionally set Reflexio config for LongMemEval extraction
    if args.setup_config:
        config = make_reflexio_config()
        logger.info("Setting Reflexio config for LongMemEval...")
        client.set_config(config)

    questions = data[args.start_idx : args.end_idx]
    logger.info(
        "Processing questions [%d:%s] (%d total)",
        args.start_idx,
        args.end_idx,
        len(questions),
    )

    ingested, skipped = 0, 0
    for question in questions:
        qid = str(question["question_id"])
        if is_ingested(args.variant, qid):
            logger.info("Skipping question %s (already ingested)", qid)
            skipped += 1
            continue
        try:
            ingest_question(client, args.variant, question, sleep_between=args.sleep)
            ingested += 1
        except Exception:
            logger.exception("Error ingesting question %s", qid)

    logger.info(
        "Done. Ingested: %d, Skipped: %d, Total: %d", ingested, skipped, len(questions)
    )


if __name__ == "__main__":
    main()
