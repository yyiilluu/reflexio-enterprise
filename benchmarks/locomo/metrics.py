"""Evaluation metrics replicating the LoCoMo paper's scoring."""

from __future__ import annotations

import re
import string

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

    common = set(pred_tokens) & set(ref_tokens)
    if not common:
        return 0.0

    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(ref_tokens)
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
