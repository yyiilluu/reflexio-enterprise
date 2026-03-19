"""Evaluation metrics replicating the LoCoMo paper's scoring."""

from __future__ import annotations

import logging
import re
import string
from collections import Counter

import litellm
from nltk.stem import PorterStemmer

_stemmer = PorterStemmer()


def _normalize(text: str) -> list[str]:
    """
    Normalize text for F1 computation: lowercase, remove articles/punctuation, stem.

    Args:
        text (str): Raw text

    Returns:
        list[str]: List of stemmed tokens
    """
    text = text.lower()
    # Remove articles
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    # Remove punctuation
    text = text.translate(str.maketrans("", "", string.punctuation))
    # Tokenize and stem
    tokens = text.split()
    return [_stemmer.stem(t) for t in tokens if t]


def token_f1(prediction: str, reference: str) -> float:
    """
    Compute token-level F1 between prediction and reference.

    Args:
        prediction (str): Model prediction
        reference (str): Gold answer

    Returns:
        float: F1 score (0.0 to 1.0)
    """
    pred_tokens = _normalize(prediction)
    ref_tokens = _normalize(reference)

    if not pred_tokens and not ref_tokens:
        return 1.0
    if not pred_tokens or not ref_tokens:
        return 0.0

    common = Counter(pred_tokens) & Counter(ref_tokens)
    num_common = sum(common.values())
    if not num_common:
        return 0.0

    precision = num_common / len(pred_tokens)
    recall = num_common / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)


def multi_hop_f1(prediction: str, reference: str) -> float:
    """
    Compute multi-hop F1: split reference by commas, average sub-answer F1 scores.

    Args:
        prediction (str): Model prediction
        reference (str): Gold answer (comma-separated sub-answers)

    Returns:
        float: Average F1 across sub-answers
    """
    sub_answers = [s.strip() for s in reference.split(",") if s.strip()]
    if not sub_answers:
        return token_f1(prediction, reference)

    scores = [token_f1(prediction, sub) for sub in sub_answers]
    return sum(scores) / len(scores)


def adversarial_accuracy(prediction: str) -> float:
    """
    Check if the prediction correctly identifies lack of information (adversarial category).

    Args:
        prediction (str): Model prediction

    Returns:
        float: 1.0 if prediction indicates "no information", 0.0 otherwise
    """
    from benchmarks.locomo.config import ADVERSARIAL_NEGATIVE_PHRASES

    pred_lower = prediction.lower()
    for phrase in ADVERSARIAL_NEGATIVE_PHRASES:
        if phrase in pred_lower:
            return 1.0
    return 0.0


def compute_score(prediction: str, reference: str, category: int) -> float:
    """
    Compute the appropriate score based on QA category.

    Args:
        prediction (str): Model prediction
        reference (str): Gold answer
        category (int): QA category (1=multi-hop, 2=single-hop, 3=temporal, 4=open-domain, 5=adversarial)

    Returns:
        float: Score (0.0 to 1.0)
    """
    if category == 5:  # adversarial
        return adversarial_accuracy(prediction)
    if category == 1:  # multi-hop
        return multi_hop_f1(prediction, reference)
    # single-hop, temporal, open-domain
    return token_f1(prediction, reference)


_logger = logging.getLogger(__name__)

_JUDGE_PROMPT = """\
You are an impartial judge evaluating a QA system's answer.

Question: {question}
Gold answer: {gold_answer}
System answer: {prediction}

Does the system answer convey the same information as the gold answer?
Minor wording differences are acceptable; the key facts must match.

Respond with exactly one line: CORRECT or WRONG, followed by a brief reason.
"""


def llm_judge_score(
    question: str,
    gold_answer: str,
    prediction: str,
    model: str = "gpt-4o-mini",
) -> float:
    """
    Use an LLM judge to evaluate whether a prediction matches the gold answer.

    For adversarial questions (category 5), use phrase-matching instead — call this
    only for non-adversarial categories.

    Args:
        question (str): The QA question
        gold_answer (str): The gold/reference answer
        prediction (str): The system's predicted answer
        model (str): LiteLLM model identifier for the judge

    Returns:
        float: 1.0 for CORRECT, 0.0 for WRONG
    """
    prompt = _JUDGE_PROMPT.format(
        question=question,
        gold_answer=gold_answer,
        prediction=prediction,
    )
    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        verdict = response.choices[0].message.content.strip()  # type: ignore[union-attr]
        _logger.debug("Judge verdict: %s", verdict)
        return 1.0 if verdict.upper().startswith("CORRECT") else 0.0
    except Exception:
        _logger.exception("LLM judge call failed")
        return 0.0


def retrieval_recall(
    evidence_texts: list[str],
    context: str,
    threshold: float = 0.3,
) -> float:
    """
    Measure what fraction of evidence turns are covered by retrieved context.

    Uses token overlap: an evidence turn is "covered" if the token overlap ratio
    between the evidence text and the context exceeds the threshold.

    Args:
        evidence_texts (list[str]): List of evidence turn texts from the dataset
        context (str): Retrieved context string
        threshold (float): Minimum token overlap ratio to consider a turn as covered

    Returns:
        float: Fraction of evidence turns covered (0.0 to 1.0)
    """
    if not evidence_texts:
        return 1.0
    if not context.strip():
        return 0.0

    context_tokens = set(_normalize(context))
    covered = 0
    for evidence in evidence_texts:
        ev_tokens = _normalize(evidence)
        if not ev_tokens:
            covered += 1
            continue
        overlap = sum(1 for t in ev_tokens if t in context_tokens)
        if overlap / len(ev_tokens) >= threshold:
            covered += 1

    return covered / len(evidence_texts)
