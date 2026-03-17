"""
Retrieve memories from Reflexio and generate answers for LongMemEval questions.

Supports three retrieval modes:
  - profile: Uses search_profiles() — tests Reflexio's core profile extraction
  - interaction: Uses search_interactions() — baseline raw retrieval
  - both: Combines profile and interaction results

Usage:
    python 02_retrieve_and_answer.py --variant oracle --data-file data/longmemeval_oracle.json --retrieval-mode profile
    python 02_retrieve_and_answer.py --variant oracle --data-file data/longmemeval_oracle.json --retrieval-mode interaction
    python 02_retrieve_and_answer.py --variant oracle --data-file data/longmemeval_oracle.json --retrieval-mode both --output output/hypotheses/oracle_both.jsonl
"""

import argparse
import json
import logging
from pathlib import Path

import litellm
from config import (
    DEFAULT_ANSWER_MODEL,
    HYPOTHESES_DIR,
    REFLEXIO_URL,
    make_user_id,
)
from dotenv import load_dotenv

from reflexio.reflexio_client.reflexio import ReflexioClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

ANSWER_SYSTEM_PROMPT = """\
You are an AI assistant answering questions about a user based on their past conversations.
You have access to extracted memories and conversation excerpts below.

Instructions:
- Answer concisely and directly based ONLY on the provided context.
- If the information needed to answer is not in the context, say "I don't know" or "I don't have that information."
- For questions about what the user currently thinks/does, use the MOST RECENT information if there are updates or corrections.
- Pay attention to dates and temporal context. The "question date" tells you when the question is being asked.
- Be specific — include names, numbers, dates when available in the context.
- Do NOT make up information or speculate beyond what the context provides.
"""


def retrieve_profiles(
    client: ReflexioClient,
    user_id: str,
    query: str,
    top_k: int = 20,
    threshold: float = 0.3,
) -> list[str]:
    """
    Retrieve profile memories from Reflexio.

    Args:
        client (ReflexioClient): The client instance
        user_id (str): User to search for
        query (str): Search query
        top_k (int): Max results
        threshold (float): Similarity threshold

    Returns:
        list[str]: List of profile content strings
    """
    try:
        resp = client.search_profiles(
            user_id=user_id,
            query=query,
            top_k=top_k,
            threshold=threshold,
        )
        if resp.success and resp.user_profiles:
            return [p.profile_content for p in resp.user_profiles]
    except Exception:
        logger.exception("search_profiles failed for user_id=%s", user_id)
    return []


def retrieve_interactions(
    client: ReflexioClient,
    user_id: str,
    query: str,
    top_k: int = 10,
) -> list[str]:
    """
    Retrieve raw interaction excerpts from Reflexio.

    Args:
        client (ReflexioClient): The client instance
        user_id (str): User to search for
        query (str): Search query
        top_k (int): Max results

    Returns:
        list[str]: List of formatted interaction strings
    """
    try:
        resp = client.search_interactions(user_id=user_id, query=query, top_k=top_k)
        if resp.success and resp.interactions:
            return [
                f"[{i.role}] {i.content}"
                for i in resp.interactions
                if i.content.strip()
            ]
    except Exception:
        logger.exception("search_interactions failed for user_id=%s", user_id)
    return []


def build_context(
    client: ReflexioClient,
    user_id: str,
    query: str,
    retrieval_mode: str,
    top_k: int = 20,
    threshold: float = 0.3,
) -> str:
    """
    Build the context string from retrieved memories.

    Args:
        client (ReflexioClient): The client instance
        user_id (str): User to search for
        query (str): Search query
        retrieval_mode (str): One of "profile", "interaction", "both"
        top_k (int): Max results per retrieval type
        threshold (float): Similarity threshold for profiles

    Returns:
        str: Formatted context block
    """
    sections = []

    if retrieval_mode in ("profile", "both"):
        profiles = retrieve_profiles(
            client, user_id, query, top_k=top_k, threshold=threshold
        )
        if profiles:
            lines = "\n".join(f"- {p}" for p in profiles)
            sections.append(
                f"## Extracted User Memories ({len(profiles)} items)\n{lines}"
            )

    if retrieval_mode in ("interaction", "both"):
        interactions = retrieve_interactions(client, user_id, query, top_k=top_k)
        if interactions:
            lines = "\n".join(interactions)
            sections.append(
                f"## Relevant Conversation Excerpts ({len(interactions)} items)\n{lines}"
            )

    return "\n\n".join(sections) if sections else "(No relevant memories found)"


def generate_answer(
    question: str,
    context: str,
    question_date: str | None,
    model: str,
) -> str:
    """
    Generate an answer using an LLM with the retrieved context.

    Args:
        question (str): The question to answer
        context (str): Retrieved memory context
        question_date (str | None): When the question is being asked
        model (str): LiteLLM model identifier

    Returns:
        str: The generated answer
    """
    user_msg_parts = []
    if question_date:
        user_msg_parts.append(f"Question date: {question_date}")
    user_msg_parts.append(f"Context:\n{context}")
    user_msg_parts.append(f"Question: {question}")

    messages = [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_msg_parts)},
    ]

    resp = litellm.completion(model=model, messages=messages, temperature=0.0)
    return resp.choices[0].message.content.strip()


def process_question(
    client: ReflexioClient,
    variant: str,
    question: dict,
    retrieval_mode: str,
    answer_model: str,
    top_k: int,
    threshold: float,
) -> dict:
    """
    Process a single LongMemEval question: retrieve context and generate answer.

    Args:
        client (ReflexioClient): The client instance
        variant (str): Dataset variant
        question (dict): Question dict from the dataset
        retrieval_mode (str): Retrieval mode
        answer_model (str): LLM model for answer generation
        top_k (int): Max retrieval results
        threshold (float): Similarity threshold

    Returns:
        dict: Result with question_id and hypothesis
    """
    question_id = str(question["question_id"])
    user_id = make_user_id(variant, question_id)
    query = question["question"]
    question_date = question.get("question_date")

    logger.info("Processing question %s: %s", question_id, query[:80])

    context = build_context(
        client, user_id, query, retrieval_mode, top_k=top_k, threshold=threshold
    )
    answer = generate_answer(query, context, question_date, answer_model)

    logger.info("  Answer: %s", answer[:120])

    return {
        "question_id": question_id,
        "hypothesis": answer,
        "retrieval_mode": retrieval_mode,
        "context_length": len(context),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retrieve and answer LongMemEval questions"
    )
    parser.add_argument(
        "--variant", required=True, help="Dataset variant (oracle, s, m)"
    )
    parser.add_argument(
        "--data-file", required=True, type=Path, help="Path to LongMemEval JSON file"
    )
    parser.add_argument(
        "--retrieval-mode",
        required=True,
        choices=["profile", "interaction", "both"],
        help="Retrieval mode",
    )
    parser.add_argument(
        "--answer-model", default=DEFAULT_ANSWER_MODEL, help="LLM model for answers"
    )
    parser.add_argument("--top-k", type=int, default=20, help="Max retrieval results")
    parser.add_argument(
        "--threshold", type=float, default=0.3, help="Similarity threshold for profiles"
    )
    parser.add_argument("--output", type=Path, default=None, help="Output JSONL path")
    parser.add_argument("--start-idx", type=int, default=0, help="Start question index")
    parser.add_argument("--end-idx", type=int, default=None, help="End question index")
    args = parser.parse_args()

    if not args.data_file.exists():
        logger.error("Data file not found: %s", args.data_file)
        return

    data = json.loads(args.data_file.read_text())
    questions = data[args.start_idx : args.end_idx]
    logger.info(
        "Processing %d questions (mode=%s, model=%s)",
        len(questions),
        args.retrieval_mode,
        args.answer_model,
    )

    output_path = args.output or (
        HYPOTHESES_DIR / f"{args.variant}_{args.retrieval_mode}.jsonl"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = ReflexioClient(url_endpoint=REFLEXIO_URL)

    with output_path.open("a") as f:
        for question in questions:
            try:
                result = process_question(
                    client,
                    args.variant,
                    question,
                    args.retrieval_mode,
                    args.answer_model,
                    args.top_k,
                    args.threshold,
                )
                f.write(json.dumps(result) + "\n")
                f.flush()
            except Exception:  # noqa: PERF203
                logger.exception(
                    "Error processing question %s", question.get("question_id")
                )

    logger.info("Results written to %s", output_path)


if __name__ == "__main__":
    main()
